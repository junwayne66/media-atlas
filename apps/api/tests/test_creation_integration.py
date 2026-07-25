"""创作链真库端到端：brief → script → timeline → compile，以及三条护栏拒绝路径。

上游蓝图由**真实分析链**（增量 2 的 AnalysisService + Fake ASR/OCR/VLM）产出，不是手搓的
——保证这条链真的接得上。DISPUTED 场景需要一个带争议事实的蓝图，用仓储直接播种（同样走
`latest_artifact` 的读取路径）。
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text

from videoforge_api.analysis_service import AnalysisService
from videoforge_api.creation import (
    BriefGenerateRequest,
    CompileRequest,
    CreationPrerequisiteMissing,
    DbCreationGateway,
    GuardrailRejected,
    ScriptGenerateRequest,
)
from videoforge_api.sources import DbSourceGateway, ImportFileRequest
from videoforge_contracts import (
    Claim,
    ClaimSourceStatus,
    CreationMode,
    CreativeTimeline,
    EvidenceSpan,
    Project,
    ProjectStatus,
    RationalTime,
    RationalTimeRange,
    RenderStage,
    RhetoricalBeat,
    RhetoricalBeatKind,
    Segment,
    SourceAsset,
    SourceAssetKind,
    SourceDisposition,
    Track,
    TrackKind,
    VideoBlueprint,
)
from videoforge_contracts.ids import new_id
from videoforge_persistence import (
    AnalysisArtifactRecord,
    AnalysisArtifactRepository,
    AnalysisRunRecord,
    AnalysisRunRepository,
    ProjectRepository,
    SourceAssetRepository,
    session_scope,
)

_NEW_TABLES = ("creative_documents", "review_decisions", "publish_jobs", "performance_snapshots")
_NOW = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_new_tables(migrated_engine: Engine) -> Iterator[None]:
    yield
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_NEW_TABLES)} CASCADE"))


@pytest.fixture()
def project(migrated_engine: Engine) -> Project:
    p = Project(
        id=new_id(),
        title="创作链演示",
        vertical="ai-tech",
        source_language="zh-CN",
        target_languages=["en-US"],
        creation_mode=CreationMode.STRUCTURE_REWRITE,
        status=ProjectStatus.DRAFT,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with session_scope(migrated_engine) as s:
        ProjectRepository(s).create(p)
    return p


@pytest.fixture()
def analyzed(migrated_engine: Engine, project: Project, tmp_path) -> SourceAsset:
    """导入真实临时文件 → 跑完整分析链 → 项目拥有 VideoBlueprint。"""
    media = tmp_path / "media" / "demo.mp4"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"fake-media-bytes")
    asset, _ = DbSourceGateway(migrated_engine).import_file(
        ImportFileRequest(path=str(media), project_id=project.id)
    )
    run = AnalysisService(migrated_engine).run(project.id, asset.id, "zh-CN")
    assert run.status == "COMPLETED"
    return asset


def _gateway(engine: Engine, tmp_path) -> DbCreationGateway:
    staging = tmp_path / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    return DbCreationGateway(engine, staging_dir=str(staging))


def _brief_request(**overrides) -> BriefGenerateRequest:
    kwargs = {
        "duration_target_ms": 45_000,
        "creation_mode": CreationMode.STRUCTURE_REWRITE,
        "target_language": "zh-CN",
    }
    kwargs.update(overrides)
    return BriefGenerateRequest(**kwargs)


def _timeline(project_id: str, source_ref: str) -> CreativeTimeline:
    def span(start: int, dur: int) -> RationalTimeRange:
        return RationalTimeRange(
            start=RationalTime(value=start, rate=30), duration=RationalTime(value=dur, rate=30)
        )

    return CreativeTimeline(
        id=new_id(),
        project_id=project_id,
        rate=30,
        duration=RationalTime(value=90, rate=30),
        tracks=[
            Track(
                id="v1",
                kind=TrackKind.V1_PRIMARY_VIDEO,
                segments=[
                    Segment(id="seg-1", time_range=span(0, 45), source_ref=source_ref),
                    Segment(id="seg-2", time_range=span(45, 45), source_ref=source_ref),
                ],
            ),
            Track(
                id="a0",
                kind=TrackKind.A0_ORIGINAL,
                segments=[Segment(id="seg-a", time_range=span(0, 90), source_ref=source_ref)],
            ),
        ],
        source_asset_ids=[source_ref],
        created_at=_NOW,
    )


def test_full_creation_chain(migrated_engine: Engine, project: Project, analyzed, tmp_path):
    gw = _gateway(migrated_engine, tmp_path)

    brief_resp = gw.generate_brief(project.id, _brief_request())
    assert brief_resp.brief_doc_version == 1 and brief_resp.claim_table_doc_version == 1
    assert brief_resp.brief.duration_target_ms == 45_000
    assert brief_resp.claim_table.entries, "蓝图应至少带一条 Claim（非空跑）"

    script_resp = gw.generate_script(project.id, ScriptGenerateRequest())
    assert script_resp.script.sentences
    assert script_resp.status == "ok" and script_resp.issues == []
    # 脚本时长贴合预算（护栏真的跑过：有源转录参与抄袭检测）
    total = sum(s.target_duration_ms for s in script_resp.script.sentences)
    assert abs(total - 45_000) <= 45_000 * 0.15

    timeline = _timeline(project.id, analyzed.id)
    tl_resp = gw.put_timeline(project.id, timeline)
    assert tl_resp.doc_version == 1

    compiled = gw.compile_timeline(project.id, CompileRequest(stage=RenderStage.FINAL))
    argv = compiled.manifest.render_graph.args
    assert argv[0] == "ffmpeg" and argv[-1].endswith("-final.mp4")
    assert analyzed.file_sha256 in compiled.manifest.input_digests.values()
    assert compiled.cache_key and compiled.doc_version == 1

    # PROXY 与 FINAL 的切点节点一致（VF-307 结构性质在 API 层仍成立）
    proxy = gw.compile_timeline(project.id, CompileRequest(stage=RenderStage.PROXY))

    def cuts(manifest):
        graph = manifest.render_graph.filter_complex
        return [
            (n.filter, n.params.get("start"), n.params.get("end"))
            for n in graph.nodes
            if n.filter in ("trim", "atrim")
        ]

    assert cuts(proxy.manifest) == cuts(compiled.manifest)
    assert proxy.cache_key != compiled.cache_key  # 阶段不同 → 缓存键不同

    assert gw.latest_document(project.id, "brief").doc_version == 1
    assert len(gw.list_documents(project.id, "render_manifest", 50)) == 2


def test_brief_without_blueprint_is_409(migrated_engine: Engine, project: Project, tmp_path):
    gw = _gateway(migrated_engine, tmp_path)
    with pytest.raises(CreationPrerequisiteMissing) as exc:
        gw.generate_brief(project.id, _brief_request())
    assert "analysis" in str(exc.value)


def test_script_without_brief_is_409(migrated_engine: Engine, project: Project, analyzed, tmp_path):
    gw = _gateway(migrated_engine, tmp_path)
    with pytest.raises(CreationPrerequisiteMissing):
        gw.generate_script(project.id, ScriptGenerateRequest())


def _seed_blueprint(engine: Engine, project_id: str, blueprint: VideoBlueprint) -> None:
    """直接播种一份蓝图产物 + run（走与分析链相同的读取路径）。"""
    with session_scope(engine) as s:
        artifact = AnalysisArtifactRecord(
            id=new_id(),
            project_id=project_id,
            kind="video_blueprint",
            cache_key=new_id().replace("-", "")[:64],
            payload=blueprint.model_dump(mode="json"),
            provider="seeded",
            tool_version="1",
            created_at=_NOW,
        )
        AnalysisArtifactRepository(s).add(artifact)
        AnalysisRunRepository(s).create(
            AnalysisRunRecord(
                id=new_id(),
                project_id=project_id,
                source_asset_id="seeded",
                language="zh-CN",
                status="COMPLETED",
                stages=[
                    {
                        "stage": "video_blueprint",
                        "status": "COMPLETED",
                        "artifact_id": artifact.id,
                    }
                ],
                created_at=_NOW,
                updated_at=_NOW,
            )
        )


def _disputed_blueprint() -> tuple[VideoBlueprint, str]:
    claim_id = "claim-disputed"
    blueprint = VideoBlueprint(
        id=new_id(),
        source_artifact_id="seeded",
        duration_ms=30_000,
        claims=[
            Claim(
                id=claim_id,
                text="该芯片性能提升 300%",
                source_status=ClaimSourceStatus.DISPUTED,
                evidence=[EvidenceSpan(kind="transcript", ref_id="seg-1", start_ms=0, end_ms=3000)],
            )
        ],
        rhetorical_beats=[
            RhetoricalBeat(id="beat-1", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=30_000)
        ],
        created_at=_NOW,
    )
    return blueprint, claim_id


def test_brief_forcing_disputed_claim_is_rejected(
    migrated_engine: Engine, project: Project, tmp_path
):
    """must_cover 强含 DISPUTED 事实 → 护栏 422，且**不落库**。"""
    blueprint, claim_id = _disputed_blueprint()
    _seed_blueprint(migrated_engine, project.id, blueprint)
    gw = _gateway(migrated_engine, tmp_path)

    with pytest.raises(GuardrailRejected) as exc:
        gw.generate_brief(project.id, _brief_request(must_cover_claim_ids=[claim_id]))
    kinds = {i.split(":")[0] for i in exc.value.issues}
    assert "MUST_COVER_CLAIM_DISPUTED" in kinds
    assert "MUST_COVER_CLAIM_NOT_USABLE" in kinds
    assert gw.list_documents(project.id, "brief", 50) == []  # 不合规输入没进库


def test_timeline_without_primary_video_track_is_rejected(
    migrated_engine: Engine, project: Project, analyzed, tmp_path
):
    gw = _gateway(migrated_engine, tmp_path)
    timeline = _timeline(project.id, analyzed.id)
    only_audio = timeline.model_copy(
        update={"tracks": [t for t in timeline.tracks if t.kind is TrackKind.A0_ORIGINAL]}
    )
    with pytest.raises(GuardrailRejected) as exc:
        gw.put_timeline(project.id, only_audio)
    assert any(i.startswith("REQUIRED_TRACK_MISSING") for i in exc.value.issues)
    assert gw.list_documents(project.id, "creative_timeline", 50) == []


def test_compile_rejects_path_escaping_whitelist(
    migrated_engine: Engine, project: Project, tmp_path
):
    """素材 local_path 含 `..` 逃出自身目录 → 编译被路径白名单拒（422）。"""
    escaping = str(tmp_path / "media" / ".." / ".." / "etc" / "passwd")
    asset = SourceAsset(
        id=new_id(),
        kind=SourceAssetKind.LOCAL_FILE,
        original_input=escaping,
        platform="manual",
        disposition=SourceDisposition.IMPORTED,
        reason="播种：路径逃逸用例",
        local_path=escaping,
        file_sha256="d" * 64,
        created_at=_NOW,
        updated_at=_NOW,
    )
    with session_scope(migrated_engine) as s:
        SourceAssetRepository(s).create(asset)
    gw = _gateway(migrated_engine, tmp_path)
    gw.put_timeline(project.id, _timeline(project.id, asset.id))

    with pytest.raises(GuardrailRejected) as exc:
        gw.compile_timeline(project.id, CompileRequest())
    assert exc.value.issues and "白名单" in exc.value.issues[0]


def test_compile_without_local_media_is_409(migrated_engine: Engine, project: Project, tmp_path):
    asset = SourceAsset(
        id=new_id(),
        kind=SourceAssetKind.URL,
        original_input="https://www.douyin.com/video/7412345678901234567",
        platform="douyin",
        disposition=SourceDisposition.MANUAL_FALLBACK,
        reason="实时下载未配置",
        created_at=_NOW,
        updated_at=_NOW,
    )
    with session_scope(migrated_engine) as s:
        SourceAssetRepository(s).create(asset)
    gw = _gateway(migrated_engine, tmp_path)
    gw.put_timeline(project.id, _timeline(project.id, asset.id))

    with pytest.raises(CreationPrerequisiteMissing) as exc:
        gw.compile_timeline(project.id, CompileRequest())
    assert "import-file" in str(exc.value)


def test_http_status_codes_for_guardrail_and_prerequisite(
    migrated_engine: Engine, project: Project, tmp_path
):
    """HTTP 面：护栏拒绝 → 422（带 issues），前置缺失 → 409。"""
    from fastapi.testclient import TestClient

    from videoforge_api.main import create_app
    from videoforge_api.settings import Settings

    url = migrated_engine.url.render_as_string(hide_password=False)
    app = create_app(Settings(database_url=url))
    app.state.creation_gateway = _gateway(migrated_engine, tmp_path)
    body = {
        "duration_target_ms": 45_000,
        "creation_mode": "STRUCTURE_REWRITE",
        "target_language": "zh-CN",
    }
    with TestClient(app) as client:
        missing = client.post(f"/v1/projects/{project.id}/brief:generate", json=body)
        assert missing.status_code == 409

        blueprint, claim_id = _disputed_blueprint()
        _seed_blueprint(migrated_engine, project.id, blueprint)
        rejected = client.post(
            f"/v1/projects/{project.id}/brief:generate",
            json={**body, "must_cover_claim_ids": [claim_id]},
        )
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["issues"]

        assert client.get(f"/v1/projects/{project.id}/brief").status_code == 404
