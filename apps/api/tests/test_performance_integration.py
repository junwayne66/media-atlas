"""效果反馈真库端到端：采集幂等 / 非 OK 不落库 / null≠0 / 样本不足不排序。

快照与发布任务通过 `external_post_id` 相连——归因特征（语言/发布小时）就从对应 Job 的元数据
取；取不到的一律 None（domain 会跳过该维度）。
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, text

from videoforge_api.demo_metrics import demo_recordings
from videoforge_api.performance import (
    CaptureRequest,
    DbPerformanceGateway,
    MetricsFetchRejected,
)
from videoforge_api.publish import DbPublishGateway, PreflightRequest, PublishJobCreate
from videoforge_contracts import (
    MetricField,
    PerformanceSnapshot,
    PublishMediaProbe,
    PublishMetadata,
    PublishPlatform,
)
from videoforge_contracts.ids import new_id
from videoforge_provider_sdk.metrics_connector import FakeMetricsConnector, MetricsFetchStatus

_NEW_TABLES = ("creative_documents", "review_decisions", "publish_jobs", "performance_snapshots")
_NOW = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)
_ACCOUNT = "acct-perf"


@pytest.fixture(autouse=True)
def _clean_new_tables(migrated_engine: Engine) -> Iterator[None]:
    yield
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_NEW_TABLES)} CASCADE"))


def _snapshot(post_id: str, age: float, views: int | None) -> PerformanceSnapshot:
    return PerformanceSnapshot(
        id=new_id(),
        platform=PublishPlatform.TIKTOK,
        platform_post_id=post_id,
        account_id=_ACCOUNT,
        observed_at=_NOW,
        age_hours=age,
        views=views,
        likes=None,  # 刻意缺失：null 语义要在 API 层看得见
        source_confidence=1.0,
    )


def _gateway(engine: Engine, recorded, **kwargs) -> DbPerformanceGateway:
    return DbPerformanceGateway(
        engine,
        connectors={
            PublishPlatform.TIKTOK: FakeMetricsConnector(
                platform=PublishPlatform.TIKTOK, recorded=recorded, **kwargs
            )
        },
    )


def test_capture_is_idempotent_and_keeps_null_metrics(migrated_engine: Engine):
    recorded = {("post-1", 24.0): _snapshot("post-1", 24.0, 15800)}
    gw = _gateway(migrated_engine, recorded)
    request = CaptureRequest(
        account_id=_ACCOUNT, platform=PublishPlatform.TIKTOK, post_id="post-1", age_hours=24.0
    )

    first = gw.capture(request)
    assert first.created and first.snapshot.views == 15800
    assert first.snapshot.likes is None  # 源没给 → 出 API 仍是 null，绝不填 0
    assert first.issues == []

    again = gw.capture(request)
    assert not again.created and again.snapshot.id == first.snapshot.id

    stored = gw.list_for_post("post-1")
    assert len(stored) == 1 and stored[0].likes is None


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"rate_limited": True}, MetricsFetchStatus.RATE_LIMITED),
        ({"auth_required": True}, MetricsFetchStatus.AUTH_REQUIRED),
        ({"fail": True}, MetricsFetchStatus.FAILED),
        ({}, MetricsFetchStatus.NOT_FOUND),  # 无录制 → 未找到
    ],
)
def test_non_ok_fetch_is_structured_and_writes_nothing(migrated_engine: Engine, kwargs, expected):
    gw = _gateway(migrated_engine, {}, **kwargs)
    with pytest.raises(MetricsFetchRejected) as exc:
        gw.capture(
            CaptureRequest(
                account_id=_ACCOUNT,
                platform=PublishPlatform.TIKTOK,
                post_id="missing",
                age_hours=1.0,
            )
        )
    assert exc.value.status is expected
    assert gw.list_for_post("missing") == []  # 不落库、不编造


def _publish_and_capture(engine: Engine, *, count: int, language: str, prefix: str) -> list[str]:
    """建真发布任务 → 提交 → 对账拿 external_post_id，供快照按帖子挂回 Job（归因特征来源）。"""
    publish_gw = DbPublishGateway(engine)
    probe = PublishMediaProbe(
        width=1080,
        height=1920,
        aspect_ratio="9:16",
        video_codec="h264",
        audio_codec="aac",
        container="mp4",
        file_size_bytes=1024,
        duration_ms=45_000,
    )
    post_ids: list[str] = []
    for i in range(count):
        metadata = PublishMetadata(title=f"{prefix}-{i}", language=language)
        job, _ = publish_gw.create(
            PublishJobCreate(
                account_id=_ACCOUNT,
                platform=PublishPlatform.TIKTOK,
                media_digest=f"{prefix}{i:062d}",
                metadata=metadata,
            )
        )
        publish_gw.preflight(job.id, PreflightRequest(probe=probe))
        publish_gw.submit(job.id)
        done = publish_gw.reconcile(job.id)
        assert done.job.external_post_id
        post_ids.append(done.job.external_post_id)
    return post_ids


def test_dashboard_groups_by_publish_metadata_and_respects_sample_floor(
    migrated_engine: Engine,
):
    zh_posts = _publish_and_capture(migrated_engine, count=3, language="zh-CN", prefix="a")
    en_posts = _publish_and_capture(migrated_engine, count=3, language="en-US", prefix="b")

    views = {
        **{p: 10_000 + i * 500 for i, p in enumerate(zh_posts)},
        **{p: 4_000 + i * 300 for i, p in enumerate(en_posts)},
    }
    recorded = {(p, 24.0): _snapshot(p, 24.0, v) for p, v in views.items()}
    # 再加一个没有对应发布任务的帖子：特征全 None，且 24h 指标缺失（null≠0）
    orphan = "orphan-post"
    recorded[(orphan, 24.0)] = _snapshot(orphan, 24.0, None)

    gw = _gateway(migrated_engine, recorded)
    for post_id, _ in recorded:
        gw.capture(
            CaptureRequest(
                account_id=_ACCOUNT,
                platform=PublishPlatform.TIKTOK,
                post_id=post_id,
                age_hours=24.0,
            )
        )

    strict = gw.dashboard(
        account_id=_ACCOUNT,
        platform=PublishPlatform.TIKTOK,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        min_samples=5,
    )
    assert strict.record_count == 7
    assert strict.issues == []
    language_groups = [g for g in strict.dashboard.group_stats if str(g.dimension) == "LANGUAGE"]
    assert {g.value for g in language_groups} == {"zh-CN", "en-US"}
    # 每组 3 条 < 5 → 只报不排
    assert all(not g.enough_samples for g in language_groups)
    assert all(str(g.dimension) != "LANGUAGE" for g in strict.ranked_groups)
    assert {g.value for g in strict.insufficient_groups} >= {"zh-CN", "en-US"}
    # 每个进入排序区的组都必须样本足够（红线：样本不足绝不排序）
    assert all(g.enough_samples for g in strict.ranked_groups)

    loose = gw.dashboard(
        account_id=_ACCOUNT,
        platform=PublishPlatform.TIKTOK,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        min_samples=3,
    )
    ranked_languages = [g for g in loose.ranked_groups if str(g.dimension) == "LANGUAGE"]
    assert [g.value for g in ranked_languages] == ["zh-CN", "en-US"]  # 相对表现降序

    # null≠0：orphan 的 views 缺失 → 不进基线样本，也没被当 0 拉低中位数
    assert loose.dashboard.baseline.sample_count == 6
    assert loose.dashboard.baseline.median is not None and loose.dashboard.baseline.median > 0


def test_learning_report_is_association_only(migrated_engine: Engine):
    posts = _publish_and_capture(migrated_engine, count=2, language="zh-CN", prefix="c")
    recorded = {(p, 24.0): _snapshot(p, 24.0, 1000 + i) for i, p in enumerate(posts)}
    gw = _gateway(migrated_engine, recorded)
    for post_id, _ in recorded:
        gw.capture(
            CaptureRequest(
                account_id=_ACCOUNT,
                platform=PublishPlatform.TIKTOK,
                post_id=post_id,
                age_hours=24.0,
            )
        )
    result = gw.learning_report(
        account_id=_ACCOUNT,
        platform=PublishPlatform.TIKTOK,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        min_samples=8,
    )
    assert result.issues == []
    assert result.report.signals
    assert all(s.association_only for s in result.report.signals)
    # 样本远不足 → 不给方向（不下结论）
    assert all(not s.enough_samples for s in result.report.signals)


def test_demo_recordings_expose_null_metrics(migrated_engine: Engine):
    """随包 demo 录制里刻意留了 null 指标——API 层要看得见"未知"而不是 0。"""
    recorded = demo_recordings(PublishPlatform.TIKTOK)
    assert recorded
    snapshot = recorded[("demo-post-a", 24.0)]
    assert snapshot.impressions is None and snapshot.saves is None
    assert snapshot.views is not None
