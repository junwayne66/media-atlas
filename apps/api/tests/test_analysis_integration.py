"""分析链真库端到端：四阶段 + 缓存命中 + 蓝图护栏 + 无本地文件 409。

关键非空跑证明：第二次同输入运行时，**Fake Provider 一次都不被调用**（用计数包装器证明），
而不仅仅是 cache_hit 标志为真。
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, select

from videoforge_api import analysis_service
from videoforge_api.analysis_service import (
    AnalysisService,
    SourceNotAnalyzable,
    UnsupportedAnalysisLanguage,
)
from videoforge_api.sources import DbSourceGateway, ImportFileRequest, ImportUrlRequest
from videoforge_contracts import (
    CreationMode,
    Project,
    ProjectStatus,
    TextTrackSet,
    Transcript,
    VideoBlueprint,
    VisualAnalysis,
)
from videoforge_contracts.ids import new_id
from videoforge_domain.blueprint import validate_blueprint
from videoforge_persistence import ProjectRepository, session_scope
from videoforge_persistence.tables import OutboxEventRow

_DOUYIN = "https://www.douyin.com/video/7412345678901234567"


@pytest.fixture()
def project(migrated_engine: Engine) -> Project:
    now = datetime(2026, 7, 25, tzinfo=UTC)
    p = Project(
        id=new_id(),
        title="演示项目",
        vertical="ai-tech",
        source_language="zh-CN",
        target_languages=["en-US"],
        creation_mode=CreationMode.STRUCTURE_REWRITE,
        status=ProjectStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    with session_scope(migrated_engine) as s:
        ProjectRepository(s).create(p)
    return p


def _imported_asset(migrated_engine: Engine, tmp_path, name: str = "demo.mp4"):
    media = tmp_path / name
    media.write_bytes(f"fake-media-{name}".encode())
    gw = DbSourceGateway(migrated_engine)
    asset, _ = gw.import_file(ImportFileRequest(path=str(media)))
    return asset


class _CountingProviderFactory:
    """包装 demo 录制工厂，统计 Fake Provider 的真实调用次数。"""

    def __init__(self, monkeypatch) -> None:
        self.calls = {"asr": 0, "ocr": 0, "vlm": 0}
        real_asr = analysis_service.load_transcripts
        real_ocr = analysis_service.load_ocr_provider
        real_vlm = analysis_service.load_vlm_provider
        outer = self

        def asr(language: str):
            provider = real_asr(language)
            transcribe = provider.transcribe

            def counted(request):
                outer.calls["asr"] += 1
                return transcribe(request)

            provider.transcribe = counted  # type: ignore[method-assign]
            return provider

        def ocr(language: str):
            provider = real_ocr(language)
            detect = provider.detect

            def counted(request):
                outer.calls["ocr"] += 1
                return detect(request)

            provider.detect = counted  # type: ignore[method-assign]
            return provider

        def vlm(language: str):
            provider = real_vlm(language)
            analyze = provider.analyze

            def counted(request):
                outer.calls["vlm"] += 1
                return analyze(request)

            provider.analyze = counted  # type: ignore[method-assign]
            return provider

        monkeypatch.setattr(analysis_service, "load_transcripts", asr)
        monkeypatch.setattr(analysis_service, "load_ocr_provider", ocr)
        monkeypatch.setattr(analysis_service, "load_vlm_provider", vlm)


def test_full_chain_completes_with_zero_blueprint_issues(
    migrated_engine: Engine, project: Project, tmp_path
) -> None:
    asset = _imported_asset(migrated_engine, tmp_path)
    svc = AnalysisService(migrated_engine)
    run = svc.run(project.id, asset.id, "zh-CN")

    assert run.status == "COMPLETED"
    assert [s["stage"] for s in run.stages] == [
        "transcript",
        "text_track_set",
        "visual_analysis",
        "video_blueprint",
    ]
    assert all(s["cache_hit"] is False for s in run.stages)  # 首跑全部真算
    assert {s["provider"] for s in run.stages} == {
        "fake-asr",
        "fake-ocr",
        "fake-vlm",
        "fake-blueprint-fusion",
    }

    transcript = Transcript.model_validate(svc.latest_artifact(project.id, "transcript"))
    tracks = TextTrackSet.model_validate(svc.latest_artifact(project.id, "text_track_set"))
    visual = VisualAnalysis.model_validate(svc.latest_artifact(project.id, "visual_analysis"))
    blueprint = VideoBlueprint.model_validate(svc.latest_artifact(project.id, "video_blueprint"))

    assert len(transcript.segments) == 3
    assert any(s.low_confidence for s in transcript.segments)  # domain 后处理真跑了
    assert {t.kind for t in tracks.tracks} == {"CAPTION", "BRAND_MARK"}
    assert visual.frames and all(f.caption for f in visual.frames)
    assert visual.vlm_provider == "fake-vlm"
    # 蓝图必须 0 issue（护栏，不是装饰）
    assert (
        validate_blueprint(
            blueprint,
            transcript_segment_ids={s.id for s in transcript.segments},
            text_track_ids={t.id for t in tracks.tracks},
        )
        == []
    )
    assert blueprint.claims and blueprint.claims[0].evidence

    with session_scope(migrated_engine) as s:
        events = [
            e.event_type
            for e in s.scalars(select(OutboxEventRow).where(OutboxEventRow.aggregate_id == run.id))
        ]
    assert events == ["analysis.completed"]


def test_second_run_hits_cache_and_never_calls_providers(
    migrated_engine: Engine, project: Project, tmp_path, monkeypatch
) -> None:
    asset = _imported_asset(migrated_engine, tmp_path)
    counter = _CountingProviderFactory(monkeypatch)
    svc = AnalysisService(migrated_engine)

    first = svc.run(project.id, asset.id, "zh-CN")
    assert first.status == "COMPLETED"
    assert counter.calls == {"asr": 1, "ocr": 1, "vlm": 1}

    second = svc.run(project.id, asset.id, "zh-CN")
    assert second.status == "COMPLETED"
    assert all(s["cache_hit"] for s in second.stages)
    assert counter.calls == {"asr": 1, "ocr": 1, "vlm": 1}  # 一次都没再调
    # 复用的是同一批产物
    assert [s["artifact_id"] for s in second.stages] == [s["artifact_id"] for s in first.stages]


def test_changing_language_recomputes_every_stage(
    migrated_engine: Engine, project: Project, tmp_path, monkeypatch
) -> None:
    asset = _imported_asset(migrated_engine, tmp_path)
    counter = _CountingProviderFactory(monkeypatch)
    svc = AnalysisService(migrated_engine)

    svc.run(project.id, asset.id, "zh-CN")
    other = svc.run(project.id, asset.id, "en-US")
    assert other.status == "COMPLETED"
    assert all(s["cache_hit"] is False for s in other.stages)  # 改语言 → 全链重算
    assert counter.calls == {"asr": 2, "ocr": 2, "vlm": 2}


def test_changing_source_asset_recomputes_downstream(
    migrated_engine: Engine, project: Project, tmp_path
) -> None:
    a = _imported_asset(migrated_engine, tmp_path, "a.mp4")
    b = _imported_asset(migrated_engine, tmp_path, "b.mp4")
    svc = AnalysisService(migrated_engine)
    svc.run(project.id, a.id, "zh-CN")
    second = svc.run(project.id, b.id, "zh-CN")
    # 素材哈希不同 → ASR 重算，并沿摘要链把下游全部带动重算
    assert all(s["cache_hit"] is False for s in second.stages)


def test_asset_without_local_file_is_conflict(migrated_engine: Engine, project: Project) -> None:
    asset, _ = DbSourceGateway(migrated_engine).import_url(ImportUrlRequest(input=_DOUYIN))
    svc = AnalysisService(migrated_engine)
    with pytest.raises(SourceNotAnalyzable) as exc:
        svc.run(project.id, asset.id, "zh-CN")
    assert "尚无本地文件" in str(exc.value)


def test_blueprint_guardrail_failure_marks_run_failed(
    migrated_engine: Engine, project: Project, tmp_path, monkeypatch
) -> None:
    """护栏不是装饰：validate_blueprint 报 issue → run FAILED，issues 落进 stages，且不落产物。"""
    from videoforge_domain.blueprint import BlueprintIssue, BlueprintIssueKind

    asset = _imported_asset(migrated_engine, tmp_path)
    monkeypatch.setattr(
        analysis_service,
        "validate_blueprint",
        lambda *a, **k: [
            BlueprintIssue(BlueprintIssueKind.LOW_COVERAGE, "rhetorical_beats", "0.10 < 0.9")
        ],
    )
    svc = AnalysisService(migrated_engine)
    run = svc.run(project.id, asset.id, "zh-CN")

    assert run.status == "FAILED"
    last = run.stages[-1]
    assert last["stage"] == "video_blueprint" and last["status"] == "FAILED"
    assert last["artifact_id"] is None
    assert any("LOW_COVERAGE" in issue for issue in last["issues"])

    with session_scope(migrated_engine) as s:
        events = [
            e.event_type
            for e in s.scalars(select(OutboxEventRow).where(OutboxEventRow.aggregate_id == run.id))
        ]
    assert events == []  # 失败不发 analysis.completed


def test_unsupported_language_is_rejected(
    migrated_engine: Engine, project: Project, tmp_path
) -> None:
    asset = _imported_asset(migrated_engine, tmp_path)
    with pytest.raises(UnsupportedAnalysisLanguage):
        AnalysisService(migrated_engine).run(project.id, asset.id, "ja-JP")
