"""创作 API（docs/modules/42 §2/§3/§8；把 P3 的 domain + Fake provider 装成 REST 面）。

链路：分析产物（VideoBlueprint）→ ClaimTable + CreativeBrief → BeatTemplate + ScriptVersion →
CreativeTimeline → FfmpegRenderGraph/RenderManifest（**只编译不渲染**）。

三条边界立场：

1. **前置缺失就 409，绝不假造上游**：没有蓝图不给 Brief，没有 Brief/ClaimTable 不给脚本，
   没有 Timeline 不给编译，素材没有本地文件不给编译——错误信息直说下一步该做什么。
2. **护栏结果分两类**：Brief / Timeline 的护栏不通过 → 422 拒绝落库（不合规的输入不该进库）；
   脚本护栏不通过 → **仍落库**并把 issues 全量返回 + `status=needs_review`——UI 要看得见问题、
   能逐句改，而不是被挡在门外（改写是迭代过程，Brief/Timeline 是结构性输入）。
3. **无真实引擎**：结构重写走 `FakeStructureRewriteProvider`（provider 字段如实写 fake-…），
   真实改写 LLM 属停止条件。编译只产 argv + manifest，**不执行 ffmpeg**。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from videoforge_api.analysis_service import AnalysisService
from videoforge_contracts import (
    BeatTemplate,
    ClaimTable,
    CreationMode,
    CreativeBrief,
    CreativeOpportunity,
    CreativeTimeline,
    RenderManifest,
    RenderStage,
    RenderTargetKind,
    ScriptVersion,
    Transcript,
    VideoBlueprint,
)
from videoforge_contracts.brief import BriefHook
from videoforge_contracts.ids import new_id
from videoforge_domain.brief import build_claim_table, build_creative_brief, validate_brief
from videoforge_domain.ffmpeg_compiler import (
    CompileConfig,
    UnsafeInputPath,
    build_render_manifest,
    compile_timeline,
    render_manifest_cache_key,
)
from videoforge_domain.rewrite import build_beat_template, validate_script
from videoforge_domain.timeline import validate_timeline
from videoforge_persistence import (
    DuplicateError,
    NotFoundError,
    ProjectRepository,
    SourceAssetRepository,
    session_scope,
)
from videoforge_persistence.creation import (
    DOC_BRIEF,
    DOC_CLAIM_TABLE,
    DOC_RENDER_MANIFEST,
    DOC_SCRIPT_VERSION,
    DOC_TIMELINE,
    CreativeDocumentRecord,
    CreativeDocumentRepository,
)
from videoforge_provider_sdk.rewrite import FakeStructureRewriteProvider, RewriteRequest

# 编译层的工具版本：本层**只编译不执行**，真实 ffmpeg 版本由 media-core RenderRuntime 在
# 渲染时探测并写进执行侧 manifest。此处如实标注是编译器版本，不冒充 ffmpeg 版本。
COMPILER_TOOL_VERSION = "ffmpeg-compiler/1"

_REWRITE_PROVIDER = "fake-structure-rewrite"


class CreationPrerequisiteMissing(Exception):
    """上游产物缺失（蓝图/Brief/时间线/本地素材）→ 409，附下一步该做什么。"""


class GuardrailRejected(Exception):
    """domain 护栏拒绝（Brief / Timeline / 编译路径）→ 422，附全量 issues。"""

    def __init__(self, message: str, issues: list[str]) -> None:
        super().__init__(message)
        self.issues = issues


def _now() -> datetime:
    return datetime.now(UTC)


# —— 请求/响应模型 ——


class HookIn(BaseModel):
    type: str = Field(min_length=1)
    promise: str = Field(min_length=1)


class BriefGenerateRequest(BaseModel):
    duration_target_ms: int = Field(gt=0)
    creation_mode: CreationMode
    target_language: str = Field(min_length=1)
    angle: str = Field(default="以实测视角讲清关键取舍", min_length=1)
    objective: str = Field(default="让目标观众在短时间内理解核心结论", min_length=1)
    audience: str = Field(default="关注 AI/科技的中文短视频观众", min_length=1)
    platform: str = Field(default="tiktok", min_length=1)
    rationale: str = Field(default="源视频已完成分析，具备可复用的节拍结构", min_length=1)
    hook: HookIn | None = None
    must_cover_claim_ids: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    cta: str | None = None


class BriefGenerateResponse(BaseModel):
    brief: CreativeBrief
    claim_table: ClaimTable
    brief_doc_version: int
    claim_table_doc_version: int


class ScriptGenerateRequest(BaseModel):
    language: str | None = Field(default=None, description="缺省用 brief.target_language")


class ScriptGenerateResponse(BaseModel):
    script: ScriptVersion
    beat_template: BeatTemplate
    doc_version: int
    status: str = Field(description="ok | needs_review（护栏有 issue 时仍落库，标 needs_review）")
    issues: list[str] = Field(default_factory=list)


class TimelinePutRequest(BaseModel):
    timeline: CreativeTimeline


class TimelinePutResponse(BaseModel):
    timeline: CreativeTimeline
    doc_version: int


class CompileRequest(BaseModel):
    stage: RenderStage = RenderStage.FINAL
    target: RenderTargetKind = RenderTargetKind.MP4_H264
    aspect_ratio: str = "9:16"


class CompileResponse(BaseModel):
    manifest: RenderManifest
    cache_key: str
    doc_version: int


class DocumentView(BaseModel):
    """产物版本的通用视图（payload 是既有合同对象的 JSON，本层不新增合同）。

    `status` / `issues` 是落库时的护栏结论：脚本护栏不过仍落库（needs_review + 全量 issues），
    GET 也看得见；brief/timeline 不过是 422 不落库，故这两项为 None/空。
    """

    id: str
    project_id: str
    kind: str
    doc_version: int
    cache_key: str | None = None
    status: str | None = None
    issues: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    payload: dict[str, Any]


def _view(record: CreativeDocumentRecord) -> DocumentView:
    return DocumentView(
        id=record.id,
        project_id=record.project_id,
        kind=record.kind,
        doc_version=record.doc_version,
        cache_key=record.cache_key,
        status=record.status,
        issues=list(record.issues),
        created_at=record.created_at,
        payload=record.payload,
    )


@dataclass(frozen=True)
class _ResolvedMedia:
    """编译输入：source_ref → 本地文件 + 哈希 + 所在目录（白名单根）。"""

    resolved_inputs: dict[str, tuple[str, str]]
    roots: tuple[str, ...]


class DbCreationGateway:
    """组合 persistence + domain + provider-sdk 的创作服务（api 是组合层）。"""

    def __init__(self, engine: Engine, *, staging_dir: str = "/tmp/videoforge/staging") -> None:
        self._engine = engine
        self._staging_dir = staging_dir

    # —— Brief ——

    def generate_brief(
        self, project_id: str, request: BriefGenerateRequest
    ) -> BriefGenerateResponse:
        blueprint = self._latest_blueprint(project_id)
        now = _now()
        with session_scope(self._engine) as s:
            project = ProjectRepository(s).get(project_id)
            docs = CreativeDocumentRepository(s)

            claim_table = build_claim_table(blueprint, table_id=new_id(), created_at=now)
            opportunity = CreativeOpportunity(
                id=new_id(),
                trend_cluster_id=project.trend_cluster_id,
                blueprint_id=blueprint.id,
                source_asset_ids=list(project.source_asset_ids),
                vertical=project.vertical,
                rationale=request.rationale,
                target_platform=request.platform,
                target_language=request.target_language,
                created_at=now,
            )
            brief = build_creative_brief(
                opportunity,
                brief_id=new_id(),
                created_at=now,
                objective=request.objective,
                audience=request.audience,
                angle=request.angle,
                duration_target_ms=request.duration_target_ms,
                creation_mode=request.creation_mode,
                claim_table=claim_table,
                hook=(
                    None
                    if request.hook is None
                    else BriefHook(type=request.hook.type, promise=request.hook.promise)
                ),
                must_cover_claim_ids=tuple(request.must_cover_claim_ids),
                avoid=tuple(request.avoid),
                cta=request.cta,
            )
            issues = validate_brief(brief, claim_table)
            if issues:
                # Brief 是结构性输入：不合规就不进库（例如强制覆盖 DISPUTED 事实）。
                raise GuardrailRejected(
                    "Brief 未通过护栏（validate_brief）",
                    [f"{i.kind}:{i.ref}:{i.detail}" for i in issues],
                )

            table_doc = docs.add(
                id=new_id(),
                project_id=project_id,
                kind=DOC_CLAIM_TABLE,
                payload=claim_table.model_dump(mode="json"),
                created_at=now,
            )
            brief_doc = docs.add(
                id=new_id(),
                project_id=project_id,
                kind=DOC_BRIEF,
                payload=brief.model_dump(mode="json"),
                created_at=now,
            )
            return BriefGenerateResponse(
                brief=brief,
                claim_table=claim_table,
                brief_doc_version=brief_doc.doc_version,
                claim_table_doc_version=table_doc.doc_version,
            )

    # —— Script ——

    def generate_script(
        self, project_id: str, request: ScriptGenerateRequest
    ) -> ScriptGenerateResponse:
        blueprint = self._latest_blueprint(project_id)
        transcript = self._latest_transcript(project_id)
        now = _now()
        with session_scope(self._engine) as s:
            ProjectRepository(s).get(project_id)
            docs = CreativeDocumentRepository(s)
            brief_doc = docs.find_latest(project_id, DOC_BRIEF)
            table_doc = docs.find_latest(project_id, DOC_CLAIM_TABLE)
            if brief_doc is None or table_doc is None:
                raise CreationPrerequisiteMissing(
                    "项目尚无 Brief/ClaimTable；请先调用 POST /v1/projects/{id}/brief:generate"
                )
            brief = CreativeBrief.model_validate(brief_doc.payload)
            claim_table = ClaimTable.model_validate(table_doc.payload)
            language = request.language or brief.target_language

            template = build_beat_template(
                blueprint,
                template_id=new_id(),
                created_at=now,
                duration_target_ms=brief.duration_target_ms,
            )
            result = FakeStructureRewriteProvider(name=_REWRITE_PROVIDER).rewrite(
                RewriteRequest(
                    script_id=new_id(),
                    created_at=now,
                    language=language,
                    beat_template=template,
                    claim_table=claim_table,
                    brief=brief,
                    source_transcript=transcript,
                )
            )
            if result.script is None:
                raise CreationPrerequisiteMissing(
                    f"结构重写未产出脚本（{result.status}）：{result.detail or '无细节'}"
                )
            issues = validate_script(
                result.script,
                claim_table=claim_table,
                source_transcript=transcript,
                brief=brief,
            )
            issue_texts = [f"{i.kind}:{i.ref}:{i.detail}" for i in issues]
            status = "needs_review" if issue_texts else "ok"
            # 脚本护栏不通过**仍落库**：UI 要看得见问题并逐句改，而不是被挡住。
            # 结论随产物一起存，GET scripts 才能看见（不是只在生成那一刻的响应里闪一下）。
            doc = docs.add(
                id=new_id(),
                project_id=project_id,
                kind=DOC_SCRIPT_VERSION,
                payload=result.script.model_dump(mode="json"),
                created_at=now,
                status=status,
                issues=issue_texts,
            )
            return ScriptGenerateResponse(
                script=result.script,
                beat_template=template,
                doc_version=doc.doc_version,
                status=status,
                issues=issue_texts,
            )

    # —— Timeline ——

    def put_timeline(self, project_id: str, timeline: CreativeTimeline) -> TimelinePutResponse:
        issues = validate_timeline(timeline)
        if issues:
            raise GuardrailRejected(
                "时间线未通过护栏（validate_timeline）",
                [f"{i.kind}:{i.ref}:{i.detail}" for i in issues],
            )
        now = _now()
        with session_scope(self._engine) as s:
            ProjectRepository(s).get(project_id)
            doc = CreativeDocumentRepository(s).add(
                id=new_id(),
                project_id=project_id,
                kind=DOC_TIMELINE,
                payload=timeline.model_dump(mode="json"),
                created_at=now,
            )
            return TimelinePutResponse(timeline=timeline, doc_version=doc.doc_version)

    def compile_timeline(self, project_id: str, request: CompileRequest) -> CompileResponse:
        now = _now()
        with session_scope(self._engine) as s:
            ProjectRepository(s).get(project_id)
            docs = CreativeDocumentRepository(s)
            tl_doc = docs.find_latest(project_id, DOC_TIMELINE)
            if tl_doc is None:
                raise CreationPrerequisiteMissing(
                    "项目尚无 CreativeTimeline；请先 POST /v1/projects/{id}/timeline"
                )
            timeline = CreativeTimeline.model_validate(tl_doc.payload)
            media = self._resolve_media(s, timeline)

            output_path = str(
                Path(self._staging_dir) / f"{timeline.id}-{str(request.stage).lower()}.mp4"
            )
            config = CompileConfig(
                output_path=output_path,
                # 白名单 = 素材所在目录 ∪ 中转目录（输出必须落在白名单内）
                allowed_input_roots=(*media.roots, self._staging_dir),
                target=request.target,
                stage=request.stage,
                aspect_ratio=request.aspect_ratio,
            )
            try:
                graph = compile_timeline(
                    timeline, media.resolved_inputs, config, COMPILER_TOOL_VERSION
                )
            except UnsafeInputPath as exc:
                raise GuardrailRejected("编译被路径白名单拒绝", [str(exc)]) from None
            except ValueError as exc:
                raise GuardrailRejected("编译参数非法", [str(exc)]) from None

            manifest = build_render_manifest(
                timeline,
                graph,
                manifest_id=new_id(),
                stage=request.stage,
                created_at=now,
                tool_version=COMPILER_TOOL_VERSION,
            )
            cache_key = render_manifest_cache_key(manifest)
            doc = docs.add(
                id=new_id(),
                project_id=project_id,
                kind=DOC_RENDER_MANIFEST,
                payload=manifest.model_dump(mode="json"),
                created_at=now,
                cache_key=cache_key,
            )
            return CompileResponse(
                manifest=manifest, cache_key=cache_key, doc_version=doc.doc_version
            )

    # —— 查询 ——

    def latest_document(self, project_id: str, kind: str) -> DocumentView:
        with session_scope(self._engine) as s:
            return _view(CreativeDocumentRepository(s).latest(project_id, kind))

    def get_document_version(self, project_id: str, kind: str, version: int) -> DocumentView:
        with session_scope(self._engine) as s:
            return _view(CreativeDocumentRepository(s).get_version(project_id, kind, version))

    def list_documents(self, project_id: str, kind: str | None, limit: int) -> list[DocumentView]:
        with session_scope(self._engine) as s:
            records = CreativeDocumentRepository(s).list(project_id, kind, limit=limit)
            return [_view(r) for r in records]

    # —— 内部 ——

    def _latest_blueprint(self, project_id: str) -> VideoBlueprint:
        try:
            payload = AnalysisService(self._engine).latest_artifact(project_id, "video_blueprint")
        except NotFoundError:
            raise CreationPrerequisiteMissing(
                "项目尚无 VideoBlueprint；请先跑分析 POST /v1/projects/{id}/analysis:run"
            ) from None
        return VideoBlueprint.model_validate(payload)

    def _latest_transcript(self, project_id: str) -> Transcript | None:
        """有转录就交给护栏做抄袭检测（非空跑）；没有则跳过该项检查。"""
        try:
            payload = AnalysisService(self._engine).latest_artifact(project_id, "transcript")
        except NotFoundError:
            return None
        return Transcript.model_validate(payload)

    @staticmethod
    def _resolve_media(session, timeline: CreativeTimeline) -> _ResolvedMedia:
        """时间线里用到的 source_ref → 素材本地文件 + sha256；缺文件即 409（不编译幻影输入）。

        白名单边界（既定立场，非疏漏）：根目录取自素材自身的 `local_path` 父目录，且
        VF-307 的 `_path_within` 只做**段级词法**归一化、**不折叠符号链接**（刻意避开
        `realpath` 的 TOCTOU）。因此素材路径某种意义上"自授权"其所在目录——这在 macOS
        桌面单用户试点下可接受：素材本就是操作者自己选的文件。多租户/服务端接入前需要
        改成集中配置的媒体根目录白名单。
        """
        refs: list[str] = []
        for track in timeline.tracks:
            for seg in track.segments:
                if seg.source_ref and seg.source_ref not in refs:
                    refs.append(seg.source_ref)
        assets = SourceAssetRepository(session)
        resolved: dict[str, tuple[str, str]] = {}
        roots: list[str] = []
        for ref in refs:
            try:
                asset = assets.get(ref)
            except NotFoundError:
                raise CreationPrerequisiteMissing(
                    f"时间线引用的素材 {ref} 不存在；请先导入素材并用其 id 作为 source_ref"
                ) from None
            if not asset.local_path or not asset.file_sha256:
                raise CreationPrerequisiteMissing(
                    f"素材 {ref} 尚无本地文件（处置 {asset.disposition}）；"
                    "请先人工下载原片并用 /v1/sources/import-file 关联后再编译"
                )
            resolved[ref] = (asset.local_path, asset.file_sha256)
            root = str(Path(asset.local_path).parent)
            if root not in roots:
                roots.append(root)
        return _ResolvedMedia(resolved_inputs=resolved, roots=tuple(roots))


router = APIRouter(prefix="/v1/projects", tags=["creation"])


def get_creation_gateway(request: Request) -> DbCreationGateway:
    return request.app.state.creation_gateway


GatewayDep = Annotated[DbCreationGateway, Depends(get_creation_gateway)]


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, GuardrailRejected):
        return HTTPException(status_code=422, detail={"message": str(exc), "issues": exc.issues})
    if isinstance(exc, CreationPrerequisiteMissing):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DuplicateError):
        # 版本号竞争重试耗尽：让调用方重试，别冒 500
        return HTTPException(status_code=409, detail=f"产物版本冲突，请重试: {exc}")
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    raise exc


@router.post("/{project_id}/brief:generate")
def generate_brief(
    project_id: str, body: BriefGenerateRequest, gateway: GatewayDep
) -> BriefGenerateResponse:
    try:
        return gateway.generate_brief(project_id, body)
    except (GuardrailRejected, CreationPrerequisiteMissing, DuplicateError, NotFoundError) as exc:
        raise _http(exc) from None


@router.post("/{project_id}/scripts:generate")
def generate_script(
    project_id: str, body: ScriptGenerateRequest, gateway: GatewayDep
) -> ScriptGenerateResponse:
    try:
        return gateway.generate_script(project_id, body)
    except (GuardrailRejected, CreationPrerequisiteMissing, DuplicateError, NotFoundError) as exc:
        raise _http(exc) from None


@router.post("/{project_id}/timeline")
def put_timeline(
    project_id: str, body: TimelinePutRequest, gateway: GatewayDep
) -> TimelinePutResponse:
    try:
        return gateway.put_timeline(project_id, body.timeline)
    except (GuardrailRejected, CreationPrerequisiteMissing, DuplicateError, NotFoundError) as exc:
        raise _http(exc) from None


@router.post("/{project_id}/timeline:compile")
def compile_project_timeline(
    project_id: str, body: CompileRequest, gateway: GatewayDep
) -> CompileResponse:
    try:
        return gateway.compile_timeline(project_id, body)
    except (GuardrailRejected, CreationPrerequisiteMissing, DuplicateError, NotFoundError) as exc:
        raise _http(exc) from None


def _get_latest(gateway: DbCreationGateway, project_id: str, kind: str) -> DocumentView:
    try:
        return gateway.latest_document(project_id, kind)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 尚无 {kind}") from None


@router.get("/{project_id}/brief")
def get_brief(project_id: str, gateway: GatewayDep) -> DocumentView:
    return _get_latest(gateway, project_id, DOC_BRIEF)


@router.get("/{project_id}/claim-table")
def get_claim_table(project_id: str, gateway: GatewayDep) -> DocumentView:
    return _get_latest(gateway, project_id, DOC_CLAIM_TABLE)


@router.get("/{project_id}/scripts")
def list_scripts(
    project_id: str,
    gateway: GatewayDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DocumentView]:
    return gateway.list_documents(project_id, DOC_SCRIPT_VERSION, limit)


@router.get("/{project_id}/scripts/{doc_version}")
def get_script_version(project_id: str, doc_version: int, gateway: GatewayDep) -> DocumentView:
    try:
        return gateway.get_document_version(project_id, DOC_SCRIPT_VERSION, doc_version)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/{project_id}/timeline")
def get_timeline(project_id: str, gateway: GatewayDep) -> DocumentView:
    return _get_latest(gateway, project_id, DOC_TIMELINE)


@router.get("/{project_id}/render-manifests")
def list_render_manifests(
    project_id: str,
    gateway: GatewayDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DocumentView]:
    return gateway.list_documents(project_id, DOC_RENDER_MANIFEST, limit)


__all__ = [
    "COMPILER_TOOL_VERSION",
    "CreationPrerequisiteMissing",
    "DbCreationGateway",
    "GuardrailRejected",
    "router",
]
