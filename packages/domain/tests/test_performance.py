"""VF-601 效果反馈 domain 测试：快照计划 + 限流 + null 语义 + 完整性护栏。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from videoforge_contracts import PerformanceSnapshot, PublishPlatform, SnapshotSchedule
from videoforge_domain import (
    DEFAULT_SNAPSHOT_AGES_HOURS,
    PerformanceIssueKind,
    can_fetch_now,
    due_snapshot_ages,
    elapsed_hours,
    is_schedule_complete,
    is_valid_performance_snapshot,
    next_allowed_fetch_time,
    next_snapshot_age,
    next_snapshot_time,
    record_capture,
    relative_to_baseline,
    validate_performance_snapshot,
)

_PUB = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def _schedule(planned=None, captured=()) -> SnapshotSchedule:
    return SnapshotSchedule(
        id="sc1",
        platform=PublishPlatform.TIKTOK,
        platform_post_id="p1",
        account_id="a1",
        published_at=_PUB,
        planned_ages_hours=list(planned or DEFAULT_SNAPSHOT_AGES_HOURS),
        captured_ages_hours=list(captured),
    )


def _snap(**over) -> PerformanceSnapshot:
    base = dict(
        id="s1",
        platform=PublishPlatform.TIKTOK,
        platform_post_id="p1",
        account_id="a1",
        observed_at=_PUB,
        age_hours=24.0,
        source_confidence=1.0,
    )
    base.update(over)
    return PerformanceSnapshot(**base)


# --- 快照计划 ---------------------------------------------------------------


def test_default_ages_match_doc():
    # §10 建议：1/3/6/24/72h/7d(=168h)
    assert DEFAULT_SNAPSHOT_AGES_HOURS == (1.0, 3.0, 6.0, 24.0, 72.0, 168.0)


def test_elapsed_hours():
    assert elapsed_hours(_PUB, _PUB + timedelta(hours=3)) == 3.0
    assert elapsed_hours(_PUB, _PUB - timedelta(hours=1)) == -1.0


def test_due_ages_only_reached_and_uncaptured():
    sch = _schedule()
    # +7h → 1,3,6 到龄；72/168 未到
    assert due_snapshot_ages(sch, _PUB + timedelta(hours=7)) == [1.0, 3.0, 6.0]
    # 已抓 1,3 → 只剩 6
    sch2 = _schedule(captured=[1.0, 3.0])
    assert due_snapshot_ages(sch2, _PUB + timedelta(hours=7)) == [6.0]


def test_due_ages_none_before_first_and_negative_elapsed():
    sch = _schedule()
    assert due_snapshot_ages(sch, _PUB + timedelta(minutes=30)) == []
    assert due_snapshot_ages(sch, _PUB - timedelta(hours=5)) == []  # now 早于发布


def test_due_ages_tolerance():
    sch = _schedule(planned=[1.0])
    # 差 5 分钟到 1h，容差 0 → 未到；容差 0.1h(6min) → 到
    at = _PUB + timedelta(minutes=55)
    assert due_snapshot_ages(sch, at) == []
    assert due_snapshot_ages(sch, at, tolerance_hours=0.1) == [1.0]


def test_next_age_and_time():
    sch = _schedule(captured=[1.0])
    assert next_snapshot_age(sch) == 3.0
    assert next_snapshot_time(sch) == _PUB + timedelta(hours=3)


def test_next_returns_none_when_all_captured():
    sch = _schedule(planned=[1.0, 3.0], captured=[1.0, 3.0])
    assert next_snapshot_age(sch) is None
    assert next_snapshot_time(sch) is None
    assert is_schedule_complete(sch)


def test_record_capture_adds_immutably_and_idempotent():
    sch = _schedule(planned=[1.0, 3.0])
    sch1 = record_capture(sch, 1.0)
    assert sch.captured_ages_hours == []  # 原对象不变
    assert 1.0 in sch1.captured_ages_hours
    sch2 = record_capture(sch1, 1.0)  # 重复标记幂等
    assert sch2.captured_ages_hours == sch1.captured_ages_hours


def test_record_capture_rejects_unplanned_age():
    sch = _schedule(planned=[1.0, 3.0])
    with pytest.raises(ValueError, match="不在 planned"):
        record_capture(sch, 99.0)


# --- 限流 -------------------------------------------------------------------


def test_can_fetch_now_boundaries():
    assert can_fetch_now(None, _PUB, 60) is True  # 从未调用
    assert can_fetch_now(_PUB, _PUB + timedelta(seconds=59), 60) is False
    assert can_fetch_now(_PUB, _PUB + timedelta(seconds=60), 60) is True  # 边界含
    assert can_fetch_now(_PUB, _PUB + timedelta(seconds=61), 60) is True


def test_next_allowed_fetch_time():
    assert next_allowed_fetch_time(None, 60) is None
    assert next_allowed_fetch_time(_PUB, 60) == _PUB + timedelta(seconds=60)


# --- null 语义（派生指标）--------------------------------------------------


def test_relative_to_baseline_null_never_zero():
    assert relative_to_baseline(200.0, 100.0) == 2.0
    assert relative_to_baseline(None, 100.0) is None  # value 未知 → None，不当 0
    assert relative_to_baseline(200.0, None) is None  # baseline 未知 → None
    assert relative_to_baseline(200.0, 0) is None  # 基线 0 → None，不做除零/顶 0


# --- 完整性护栏（null-aware）------------------------------------------------


def test_clean_snapshot_no_issues():
    s = _snap(views=1000, likes=50, comments=10, impressions=2000, completion_rate=0.5)
    assert validate_performance_snapshot(s) == []
    assert is_valid_performance_snapshot(s)


def test_null_views_does_not_trip_engagement_check():
    # KEY §10 null 语义：views=None（未知）时，likes=500 绝不判 likes>views(=0)
    s = _snap(likes=500, comments=300)
    assert validate_performance_snapshot(s) == []


def test_engagement_exceeds_views_fires_only_when_both_known():
    s = _snap(views=100, likes=500)
    kinds = {i.kind for i in validate_performance_snapshot(s)}
    assert PerformanceIssueKind.ENGAGEMENT_EXCEEDS_VIEWS in kinds


def test_views_exceed_impressions():
    s = _snap(views=5000, impressions=1000)
    kinds = {i.kind for i in validate_performance_snapshot(s)}
    assert PerformanceIssueKind.VIEWS_EXCEED_IMPRESSIONS in kinds
    # impressions 未知 → 不触发
    assert not any(
        i.kind is PerformanceIssueKind.VIEWS_EXCEED_IMPRESSIONS
        for i in validate_performance_snapshot(_snap(views=5000))
    )


def test_completion_rate_with_zero_views_is_contradiction_but_null_views_ok():
    # views=0 明确 + 有完成率 → 矛盾
    bad = _snap(views=0, completion_rate=0.5)
    assert any(
        i.kind is PerformanceIssueKind.COMPLETION_RATE_WITHOUT_VIEWS
        for i in validate_performance_snapshot(bad)
    )
    # views=None（未知）+ 有完成率 → 不触发（null≠0）
    ok = _snap(completion_rate=0.5)
    assert not any(
        i.kind is PerformanceIssueKind.COMPLETION_RATE_WITHOUT_VIEWS
        for i in validate_performance_snapshot(ok)
    )
