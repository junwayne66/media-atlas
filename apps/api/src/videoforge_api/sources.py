"""来源素材 API（docs/modules/41 §2/§3；补齐 VF-105/VF-107 遗留的 REST 面）。

路由是 gateway 的薄封装；gateway 组合 persistence（SourceAssetRepository / ProjectRepository）、
provider-sdk（url_resolver + DownloadRouter）、media-core（流式 sha256）与 domain（去重）。

**安全立场（README §4 / 53 §10）：全程无 live network。** 下载连接器按默认构造装配（runner 与
cookie resolver 均为 Unconfigured），因此路由必然走到 manual_fallback——这不是「失败」，而是
诚实的「实时下载未配置，请人工下载后关联」，并把可解释的 attempts 轨迹落进素材记录。
短链展开同样需要网络，默认不展开，标记 NEEDS_EXPANSION。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from videoforge_connector_f2 import F2DownloadConnector
from videoforge_connector_yt_dlp import YtDlpDownloadConnector
from videoforge_contracts import (
    AcquisitionAttemptSummary,
    AcquisitionSummary,
    SourceAsset,
    SourceAssetKind,
    SourceDisposition,
)
from videoforge_contracts.ids import new_id
from videoforge_domain.dedup import AssetFingerprint, find_duplicate_groups
from videoforge_media_core.hashing import sha256_file
from videoforge_persistence import (
    DuplicateError,
    NotFoundError,
    ProjectRepository,
    SourceAssetRepository,
    VersionConflictError,
    record_event,
    session_scope,
    source_input_digest,
)
from videoforge_provider_sdk import (
    DownloadRequest,
    DownloadRouter,
    UnresolvableUrl,
    resolve_local_file,
    resolve_url,
)

# —— 请求/响应模型 ——


class ResolveRequest(BaseModel):
    input: str = Field(min_length=1, description="链接 / 分享文本")


class ResolveResponse(BaseModel):
    """纯预览（不落库）：解析结果 + 明确的可导入性判断。"""

    resolvable: bool
    platform: str
    content_id: str | None = None
    canonical_url: str | None = None
    needs_expansion: bool = False
    short_url: str | None = None
    reason: str
    error_code: str | None = None


class ImportUrlRequest(BaseModel):
    input: str = Field(min_length=1)
    project_id: str | None = None


class ImportFileRequest(BaseModel):
    path: str = Field(min_length=1)
    project_id: str | None = None


class DuplicateGroupView(BaseModel):
    group_id: str
    member_asset_ids: list[str]
    layers: list[str]
    similarity: float


class SourceGateway(Protocol):
    def resolve(self, request: ResolveRequest) -> ResolveResponse: ...
    def import_url(self, request: ImportUrlRequest) -> tuple[SourceAsset, bool]: ...
    def import_file(self, request: ImportFileRequest) -> tuple[SourceAsset, bool]: ...
    def list_assets(
        self, platform: str | None, disposition: SourceDisposition | None, limit: int
    ) -> list[SourceAsset]: ...
    def get_asset(self, asset_id: str) -> SourceAsset: ...
    def duplicate_groups(self) -> list[DuplicateGroupView]: ...


class LocalFileMissing(ValueError):
    """手工导入指向的本地文件不存在（422，不静默建一条无文件的「已导入」素材）。"""


class ProjectAttachConflict(RuntimeError):
    """有界重试后仍与并发写冲突（409，让调用方重试；绝不静默丢失项目关联）。"""


_ATTACH_MAX_ATTEMPTS = 3


def default_download_router() -> DownloadRouter:
    """默认下载路由：真实连接器 + 默认（未配置）runner —— 不触网，只产出可解释轨迹。"""
    return DownloadRouter(
        {
            "download.f2": F2DownloadConnector(),
            "download.yt_dlp": YtDlpDownloadConnector(),
        }
    )


def _now() -> datetime:
    return datetime.now(UTC)


class DbSourceGateway:
    def __init__(self, engine: Engine, *, router: DownloadRouter | None = None) -> None:
        self._engine = engine
        self._router = router or default_download_router()

    # —— 解析预览（零 I/O、零网络）——

    def resolve(self, request: ResolveRequest) -> ResolveResponse:
        try:
            resolved = resolve_url(request.input)
        except UnresolvableUrl as exc:
            return ResolveResponse(
                resolvable=False,
                platform="unknown",
                reason=str(exc),
                error_code="UNRESOLVABLE_INPUT",
            )
        if resolved.needs_expansion:
            return ResolveResponse(
                resolvable=False,
                platform=resolved.platform,
                needs_expansion=True,
                short_url=resolved.short_url,
                reason="短链需先展开（展开需实时网络，默认未启用）；请粘贴规范链接或手工导入",
                error_code="NEEDS_EXPANSION",
            )
        return ResolveResponse(
            resolvable=True,
            platform=resolved.platform,
            content_id=resolved.content_id,
            canonical_url=resolved.canonical_url,
            reason="已识别平台与内容 ID",
        )

    # —— 导入 ——

    def import_url(self, request: ImportUrlRequest) -> tuple[SourceAsset, bool]:
        """返回 (素材, 是否新建)。

        幂等身份分两类：可解析链接按 (platform, content_id)；短链 / 不可解析输入没有
        content_id，按 sha256(原始输入) 去重——否则同一短链导入 N 次会得到 N 条资产
        与 N 个 `source.imported` 事件。两类都在 `_import_idempotent` 里「先查后建、
        撞唯一索引再重查复用」，并发下不会有一方 500。
        """
        try:
            resolved = resolve_url(request.input)
        except UnresolvableUrl as exc:
            # 在 except 块外仍要用到原因文本：Python 会在块结束时清掉 exc，先取出字符串
            reason = str(exc)
            return self._import_idempotent(
                lookup=lambda repo: repo.find_existing(
                    input_digest=source_input_digest(request.input)
                ),
                make_asset=lambda: self._new_asset(
                    kind=SourceAssetKind.URL,
                    original_input=request.input,
                    platform="unknown",
                    disposition=SourceDisposition.UNRESOLVABLE,
                    reason=reason,
                    error_code="UNRESOLVABLE_INPUT",
                ),
                project_id=request.project_id,
            )

        if resolved.needs_expansion:
            return self._import_idempotent(
                lookup=lambda repo: repo.find_existing(
                    input_digest=source_input_digest(request.input)
                ),
                make_asset=lambda: self._new_asset(
                    kind=SourceAssetKind.URL,
                    original_input=request.input,
                    platform=resolved.platform,
                    canonical_url=resolved.short_url,
                    disposition=SourceDisposition.NEEDS_EXPANSION,
                    reason="短链需先展开（展开需实时网络，默认未启用）；请粘贴规范链接或手工导入",
                    error_code="NEEDS_EXPANSION",
                ),
                project_id=request.project_id,
            )

        def make_downloaded_asset() -> SourceAsset:
            # 未命中 → 走下载路由（默认全未配置，必然 manual_fallback）
            route = self._router.download(
                DownloadRequest(source=resolved, dest_dir=Path("/nonexistent-dest"))
            )
            attempts = [
                AcquisitionAttemptSummary(
                    connector=a.connector,
                    status=str(a.status),
                    error_code=None if a.error_code is None else str(a.error_code),
                )
                for a in route.attempts
            ]
            acquisition = AcquisitionSummary(
                tool_name="download.router",
                attempts=attempts,
                manual_fallback=route.manual_fallback,
            )
            return self._new_asset(
                kind=SourceAssetKind.URL,
                original_input=request.input,
                platform=resolved.platform,
                content_id=resolved.content_id,
                canonical_url=resolved.canonical_url,
                disposition=SourceDisposition.MANUAL_FALLBACK,
                reason="实时下载未配置（需真实账号/凭据）；请人工下载原片后用 import-file 关联",
                error_code=(
                    None if route.result.error_code is None else str(route.result.error_code)
                ),
                acquisition=acquisition,
            )

        return self._import_idempotent(
            lookup=lambda repo: repo.find_existing(
                platform=resolved.platform, content_id=resolved.content_id
            ),
            make_asset=make_downloaded_asset,
            project_id=request.project_id,
        )

    def import_file(self, request: ImportFileRequest) -> tuple[SourceAsset, bool]:
        resolved = resolve_local_file(request.path)
        path = Path(request.path)
        if not path.is_file():
            raise LocalFileMissing(f"本地文件不存在：{request.path}")
        digest, size = sha256_file(path)
        del size  # 仅用于流式哈希的副产物，不入合同（Artifact 层才关心字节数）

        return self._import_idempotent(
            lookup=lambda repo: repo.find_existing(file_sha256=digest),
            make_asset=lambda: self._new_asset(
                kind=SourceAssetKind.LOCAL_FILE,
                original_input=request.path,
                platform=resolved.platform,  # manual
                content_id=resolved.content_id,
                canonical_url=resolved.canonical_url,
                disposition=SourceDisposition.IMPORTED,
                reason="本地原片已导入并完成哈希校验",
                local_path=str(path),
                file_sha256=digest,
                acquisition=AcquisitionSummary(
                    tool_name="manual.import", output_sha256=digest, manual_fallback=False
                ),
            ),
            project_id=request.project_id,
        )

    # —— 查询 ——

    def list_assets(
        self, platform: str | None, disposition: SourceDisposition | None, limit: int
    ) -> list[SourceAsset]:
        with session_scope(self._engine) as s:
            return SourceAssetRepository(s).list(
                platform=platform, disposition=disposition, limit=limit
            )

    def get_asset(self, asset_id: str) -> SourceAsset:
        with session_scope(self._engine) as s:
            return SourceAssetRepository(s).get(asset_id)

    def duplicate_groups(self) -> list[DuplicateGroupView]:
        """FILE 层去重（有 file_sha256 的素材）。只建组，绝不删除任何来源记录（41 §5）。"""
        with session_scope(self._engine) as s:
            assets = SourceAssetRepository(s).list_with_file_hash()
        fingerprints = [AssetFingerprint(asset_id=a.id, sha256=a.file_sha256 or "") for a in assets]
        return [
            DuplicateGroupView(
                group_id=g.group_id,
                member_asset_ids=list(g.member_asset_ids),
                layers=[str(layer) for layer in g.layers],
                similarity=g.similarity,
            )
            for g in find_duplicate_groups(fingerprints)
        ]

    # —— 内部 ——

    def _new_asset(
        self,
        *,
        kind: SourceAssetKind,
        original_input: str,
        platform: str,
        disposition: SourceDisposition,
        reason: str,
        content_id: str | None = None,
        canonical_url: str | None = None,
        error_code: str | None = None,
        local_path: str | None = None,
        file_sha256: str | None = None,
        acquisition: AcquisitionSummary | None = None,
    ) -> SourceAsset:
        now = _now()
        return SourceAsset(
            id=new_id(),
            kind=kind,
            original_input=original_input,
            platform=platform,
            content_id=content_id or None,
            canonical_url=canonical_url or None,
            disposition=disposition,
            reason=reason,
            error_code=error_code,
            local_path=local_path,
            file_sha256=file_sha256,
            acquisition=acquisition,
            created_at=now,
            updated_at=now,
        )

    def _import_idempotent(
        self,
        *,
        lookup: Callable[[SourceAssetRepository], SourceAsset | None],
        make_asset: Callable[[], SourceAsset],
        project_id: str | None,
    ) -> tuple[SourceAsset, bool]:
        """先查后建的幂等导入。

        查与建在两个事务里，中间有并发窗口：两方都 miss 时会双插，部分唯一索引拒掉后者。
        输家不应 500——它重查（此时赢家必已提交，否则 INSERT 会阻塞而非报错）并复用同一
        素材，得到与「命中复用」完全一致的 200 语义（created=False）。
        """
        with session_scope(self._engine) as s:
            existing = lookup(SourceAssetRepository(s))
            if existing is not None:
                return self._attach_project(s, existing, project_id), False

        try:
            return self._persist_new(make_asset(), project_id), True
        except (DuplicateError, IntegrityError):
            with session_scope(self._engine) as s:
                existing = lookup(SourceAssetRepository(s))
                if existing is None:
                    raise  # 不是幂等冲突（如主键碰撞）→ 如实上抛，不掩盖
                return self._attach_project(s, existing, project_id), False

    def _persist_new(self, asset: SourceAsset, project_id: str | None) -> SourceAsset:
        if project_id:
            asset = asset.model_copy(update={"project_ids": [project_id]})
        with session_scope(self._engine) as s:
            SourceAssetRepository(s).create(asset)
            # 同事务写 outbox（与领域写一起提交或一起回滚）
            record_event(
                s,
                aggregate_type="source_asset",
                aggregate_id=asset.id,
                event_type="source.imported",
                payload=asset.model_dump(mode="json"),
            )
            if project_id:
                self._link_project(s, project_id, asset.id)
        return asset

    def _attach_project(
        self, session: Session, asset: SourceAsset, project_id: str | None
    ) -> SourceAsset:
        """幂等命中路径：只在需要时把素材挂到 Project（去重），不重复建记录。

        两个请求给同一素材挂**不同** project 时会撞乐观锁：输家不能 500 也不能静默丢关联，
        必须重读最新版本、在最新 project_ids 上重新追加（去重）后重试。有界重试仍冲突 →
        ProjectAttachConflict（409，让调用方重试），绝不无限自旋。
        """
        if not project_id or project_id in asset.project_ids:
            return asset
        repo = SourceAssetRepository(session)
        for _ in range(_ATTACH_MAX_ATTEMPTS):
            try:
                updated = repo.update(
                    asset.model_copy(update={"project_ids": [*asset.project_ids, project_id]}),
                    expected_version=asset.version,
                )
            except VersionConflictError:
                # 重读：expire 掉本事务身份映射里的旧行，READ COMMITTED 下能看到赢家的提交
                session.expire_all()
                asset = repo.get(asset.id)
                if project_id in asset.project_ids:
                    return asset  # 并发方已挂上同一 project → 无需再写
                continue
            self._link_project(session, project_id, asset.id)
            return updated
        raise ProjectAttachConflict(f"素材 {asset.id} 并发写冲突，请重试")

    def _link_project(self, session: Session, project_id: str, asset_id: str) -> None:
        """反向关联：把素材挂进 Project.source_asset_ids（去重）。

        与 `_attach_project` 同一模式的有界重试：「批量导入进同一项目」是 UI 高频路径，
        两个请求并发挂**不同素材**到同一 Project 会撞 Project 行的乐观锁，输家必须重读最新
        Project 版本重新追加，而不是 500。耗尽 → ProjectAttachConflict（409）。
        """
        repo = ProjectRepository(session)
        for _ in range(_ATTACH_MAX_ATTEMPTS):
            try:
                project = repo.get(project_id)
            except NotFoundError:
                return  # Project 不存在时不阻断素材导入（素材可先于项目存在）
            if asset_id in project.source_asset_ids:
                return  # 已挂（含并发方已代为挂上）→ 幂等返回
            try:
                repo.update(
                    project.model_copy(
                        update={"source_asset_ids": [*project.source_asset_ids, asset_id]}
                    ),
                    expected_version=project.version,
                )
            except VersionConflictError:
                # 重读：expire 掉本事务身份映射里的旧行，READ COMMITTED 下能看到赢家的提交
                session.expire_all()
                continue
            return
        raise ProjectAttachConflict(f"项目 {project_id} 并发写冲突，请重试")


# 前缀只到 /v1：`/sources:resolve` 是动作式路径（51 §4），不能作为 /v1/sources 的子路径
router = APIRouter(prefix="/v1", tags=["sources"])


def get_source_gateway(request: Request) -> SourceGateway:
    return request.app.state.source_gateway


GatewayDep = Annotated[SourceGateway, Depends(get_source_gateway)]


@router.post("/sources:resolve")
def resolve_source(body: ResolveRequest, gateway: GatewayDep) -> ResolveResponse:
    return gateway.resolve(body)


@router.post("/sources/import-url")
def import_url(body: ImportUrlRequest, gateway: GatewayDep, response: Response) -> SourceAsset:
    try:
        asset, created = gateway.import_url(body)
    except ProjectAttachConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    response.status_code = 201 if created else 200
    return asset


@router.post("/sources/import-file")
def import_file(body: ImportFileRequest, gateway: GatewayDep, response: Response) -> SourceAsset:
    try:
        asset, created = gateway.import_file(body)
    except (LocalFileMissing, UnresolvableUrl) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ProjectAttachConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    response.status_code = 201 if created else 200
    return asset


@router.get("/sources/duplicate-groups")
def list_duplicate_groups(gateway: GatewayDep) -> list[DuplicateGroupView]:
    return gateway.duplicate_groups()


@router.get("/sources")
def list_sources(
    gateway: GatewayDep,
    platform: str | None = None,
    disposition: SourceDisposition | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[SourceAsset]:
    return gateway.list_assets(platform, disposition, limit)


@router.get("/sources/{asset_id}")
def get_source(asset_id: str, gateway: GatewayDep) -> SourceAsset:
    try:
        return gateway.get_asset(asset_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"source asset 不存在: {asset_id}") from None
