"""合成时间序列验证 velocity / acceleration / decay（VF-101 DoD）。"""

import pytest
from trend_factories import snapshot_series

from videoforge_contracts import TrendItemSnapshot
from videoforge_domain import (
    InsufficientSnapshots,
    decline_from_peak,
    engagement_efficiency,
    series_acceleration,
    series_velocity,
)


def test_velocity_positive_for_rising_series() -> None:
    # 每小时 +200/+400/+800，最近一段 800/h
    v = series_velocity(snapshot_series([100, 300, 700, 1500]))
    assert v == pytest.approx(800.0)


def test_velocity_negative_for_declining_last_segment() -> None:
    v = series_velocity(snapshot_series([1500, 1500, 1200]))
    assert v == pytest.approx(-300.0)


def test_acceleration_positive_when_taking_off() -> None:
    # 一阶差 200,400,800 → 最近加速度 800-400=400（步长 1h）
    a = series_acceleration(snapshot_series([100, 300, 700, 1500]))
    assert a == pytest.approx(400.0)


def test_acceleration_zero_for_linear_growth() -> None:
    a = series_acceleration(snapshot_series([100, 200, 300, 400]))
    assert a == pytest.approx(0.0)


def test_acceleration_negative_when_decelerating() -> None:
    # 一阶差 800,400,100 → 最近 100-400=-300
    a = series_acceleration(snapshot_series([0, 800, 1200, 1300]))
    assert a == pytest.approx(-300.0)


def test_decline_from_peak_zero_while_rising() -> None:
    assert decline_from_peak(snapshot_series([100, 300, 700, 1500])) == pytest.approx(0.0)


def test_decline_from_peak_half_after_dropping() -> None:
    # 峰值 1000，末值 500 → 回落 50%
    assert decline_from_peak(snapshot_series([200, 1000, 500])) == pytest.approx(0.5)


def test_missing_metric_snapshots_skipped() -> None:
    # 只有两个有 views 的点，中间 null 被跳过
    v = series_velocity(snapshot_series([100, None, 500]))
    # 有效点 (t0,100),(t2,500)，间隔 2h → 200/h
    assert v == pytest.approx(200.0)


def test_velocity_needs_two_points() -> None:
    with pytest.raises(InsufficientSnapshots):
        series_velocity(snapshot_series([100]))


def test_acceleration_needs_three_points() -> None:
    with pytest.raises(InsufficientSnapshots):
        series_acceleration(snapshot_series([100, 200]))


def test_engagement_efficiency_zero_without_views() -> None:
    snap = TrendItemSnapshot(
        id="s",
        observed_at=snapshot_series([1])[0].observed_at,
        platform="douyin",
        item_id="i",
        collector_version="t",
        source_confidence=1.0,
        views=None,
        likes=100,
    )
    assert engagement_efficiency(snap) == 0.0


def test_engagement_efficiency_rewards_smaller_account() -> None:
    base = dict(
        id="s",
        observed_at=snapshot_series([1])[0].observed_at,
        platform="douyin",
        item_id="i",
        collector_version="t",
        source_confidence=1.0,
        views=10000,
        likes=1000,
        comments=200,
        shares=100,
        saves=100,
    )
    small = engagement_efficiency(TrendItemSnapshot(**base, followers_at_observation=500))
    huge = engagement_efficiency(TrendItemSnapshot(**base, followers_at_observation=5_000_000))
    assert 0.0 < huge < small <= 1.0
