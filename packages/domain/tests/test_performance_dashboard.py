"""VF-602 效果看板 domain 测试：账号内相对指标 + 分组 + 样本不足不排 + null≠0 + 确定性。"""

from __future__ import annotations

from datetime import UTC, datetime

from videoforge_contracts import (
    AccountBaselineEntry,
    CreationMode,
    GroupDimension,
    MetricField,
    PerformanceDashboard,
    PerformanceFeatures,
    PerformanceGroupStat,
    PerformanceSnapshot,
    PublishPlatform,
    VideoPerformanceRecord,
)
from videoforge_domain import (
    DashboardIssueKind,
    bucket_for,
    build_account_baseline,
    build_dashboard,
    compute_account_baseline_entry,
    duration_bucket,
    insufficient_sample_groups,
    metric_value_at_age,
    percentile,
    publish_daypart,
    rank_groups,
    relative_value,
    validate_dashboard,
    validate_records_single_account,
)

_T = datetime(2026, 7, 26, tzinfo=UTC)
_TK = PublishPlatform.TIKTOK


def _snap(views, *, age=24.0, observed=_T) -> PerformanceSnapshot:
    return PerformanceSnapshot(
        id="s", platform=_TK, platform_post_id="p", account_id="a1",
        observed_at=observed, age_hours=age, views=views, source_confidence=1.0,
    )


def _rec(rid, views, *, tmpl="T1", dur=45000, acct="a1", hour=20,
          mode=CreationMode.STRUCTURE_REWRITE) -> VideoPerformanceRecord:
    feats = PerformanceFeatures(template_id=tmpl, creation_mode=mode,
                                 duration_ms=dur, language="zh-CN", publish_hour=hour)
    snaps = [_snap(views)] if views is not None else []
    return VideoPerformanceRecord(id=rid, account_id=acct, platform=_TK,
                                   published_at=_T, features=feats, snapshots=snaps)


# --- 统计原语 --------------------------------------------------------------

def test_percentile_linear_interp():
    assert percentile([], 0.5) is None
    assert percentile([42.0], 0.5) == 42.0
    assert percentile([100.0, 200.0], 0.5) == 150.0
    assert percentile([100.0, 200.0, 300.0], 0.5) == 200.0
    # p25 of [0,100,200,300]: h=(4-1)*0.25=0.75 → 0 + 0.75*100 = 75
    assert percentile([0.0, 100.0, 200.0, 300.0], 0.25) == 75.0


# --- 取值 / 相对 ------------------------------------------------------------

def test_metric_value_at_age_latest_and_missing():
    r = VideoPerformanceRecord(
        id="r", account_id="a1", platform=_TK, published_at=_T,
        features=PerformanceFeatures(),
        snapshots=[_snap(100, observed=_T), _snap(120, observed=datetime(2026, 7, 27, tzinfo=UTC))],
    )
    assert metric_value_at_age(r, 24.0, MetricField.VIEWS) == 120  # 取最新观测
    assert metric_value_at_age(r, 72.0, MetricField.VIEWS) is None  # 无该年龄
    assert metric_value_at_age(r, 24.0, MetricField.LIKES) is None  # 指标缺失


def test_relative_value_null_safe():
    r = _rec("r", 300)
    assert relative_value(r, 150.0, 24.0, MetricField.VIEWS) == 2.0
    assert relative_value(r, None, 24.0, MetricField.VIEWS) is None  # 无基线 → None
    assert relative_value(_rec("r2", None), 150.0, 24.0, MetricField.VIEWS) is None


# --- 分桶 ------------------------------------------------------------------

def test_duration_bucket_boundaries():
    assert duration_bucket(0) == "0-30s"
    assert duration_bucket(29_999) == "0-30s"
    assert duration_bucket(30_000) == "30-60s"  # 边界归入下一桶 [lo,hi)
    assert duration_bucket(90_000) == "90s+"
    assert duration_bucket(None) is None


def test_publish_daypart():
    assert publish_daypart(0) == "夜间(0-6)"
    assert publish_daypart(6) == "上午(6-12)"
    assert publish_daypart(20) == "晚间(18-24)"
    assert publish_daypart(None) is None


def test_bucket_for_none_feature_skips():
    empty = PerformanceFeatures()
    for dim in GroupDimension:
        assert bucket_for(dim, empty) is None
    feats = PerformanceFeatures(template_id="T1", creation_mode=CreationMode.SOURCE_REEDIT,
                                 duration_ms=45000, language="en-US", publish_hour=3)
    assert bucket_for(GroupDimension.CREATION_MODE, feats) == "SOURCE_REEDIT"
    assert bucket_for(GroupDimension.DURATION_BUCKET, feats) == "30-60s"
    assert bucket_for(GroupDimension.PUBLISH_DAYPART, feats) == "夜间(0-6)"


# --- 基线：null≠0（红线）---------------------------------------------------

def test_baseline_excludes_null_never_zero():
    # [None, 100, 200] → median 150（排除 None），绝不是把 None 当 0 的 median≈100
    recs = [_rec("r1", None), _rec("r2", 100), _rec("r3", 200)]
    b = compute_account_baseline_entry(recs, 24.0, MetricField.VIEWS)
    assert b.median == 150.0 and b.sample_count == 2


def test_build_account_baseline_filters_account():
    recs = [_rec("a", 100), _rec("b", 200), _rec("c", 9999, acct="other")]
    bl = build_account_baseline(recs, account_id="a1", platform=_TK,
                                 generated_at=_T, ages_hours=[24.0],
                                 metrics=[MetricField.VIEWS])
    assert bl.entries[0].sample_count == 2  # other 账号被排除
    assert bl.entries[0].median == 150.0


# --- 看板：账号内相对（红线）------------------------------------------------

def test_dashboard_is_account_relative_not_absolute():
    # 账号 A（100/200，median 150）与账号 B（1000/2000，median 1500）绝对差 10x，
    # 相对模式相同 → 同一相对看板。
    a = [_rec("a1v", 100), _rec("a2v", 200)]
    b = [_rec("b1v", 1000, acct="b1"), _rec("b2v", 2000, acct="b1")]
    da = build_dashboard(a + b, account_id="a1", platform=_TK, age_hours=24.0,
                          metric=MetricField.VIEWS, generated_at=_T, min_samples=2)
    db = build_dashboard(a + b, account_id="b1", platform=_TK, age_hours=24.0,
                          metric=MetricField.VIEWS, generated_at=_T, min_samples=2)
    assert da.baseline.median == 150.0 and db.baseline.median == 1500.0
    ga = next(g for g in da.group_stats if g.dimension is GroupDimension.TEMPLATE)
    gb = next(g for g in db.group_stats if g.dimension is GroupDimension.TEMPLATE)
    assert ga.median_relative == gb.median_relative == 1.0
    assert ga.sample_count == 2  # 账号内，B 记录不混入


def test_build_dashboard_deterministic():
    recs = [_rec(f"r{i}", 100 + i) for i in range(6)]
    d1 = build_dashboard(recs, account_id="a1", platform=_TK, age_hours=24.0,
                          metric=MetricField.VIEWS, generated_at=_T)
    d2 = build_dashboard(recs, account_id="a1", platform=_TK, age_hours=24.0,
                          metric=MetricField.VIEWS, generated_at=_T)
    assert d1.model_dump() == d2.model_dump()


# --- 样本不足不排序（红线）-------------------------------------------------

def test_small_sample_never_ranked():
    recs = [_rec("rare", 5000, tmpl="RARE")] + [
        _rec(f"m{i}", 100 + i, tmpl="COMMON") for i in range(6)]
    d = build_dashboard(recs, account_id="a1", platform=_TK, age_hours=24.0,
                         metric=MetricField.VIEWS, generated_at=_T, min_samples=5)
    rare = next(g for g in d.group_stats
                if g.dimension is GroupDimension.TEMPLATE and g.value == "RARE")
    assert rare.sample_count == 1 and rare.enough_samples is False
    ranked = rank_groups(d, GroupDimension.TEMPLATE)
    # RARE 的相对值最高，但样本不足 → 绝不出现在排序里
    assert [g.value for g in ranked] == ["COMMON"]
    assert rare in insufficient_sample_groups(d)


def test_rank_groups_sorted_desc_only_eligible():
    # 三个模板各 5 样本，相对值不同 → 降序
    recs = []
    for tmpl, base in (("LOW", 50), ("HIGH", 300), ("MID", 150)):
        recs += [_rec(f"{tmpl}{i}", base + i, tmpl=tmpl) for i in range(5)]
    d = build_dashboard(recs, account_id="a1", platform=_TK, age_hours=24.0,
                         metric=MetricField.VIEWS, generated_at=_T, min_samples=5)
    ranked = rank_groups(d, GroupDimension.TEMPLATE)
    vals = [g.value for g in ranked]
    assert vals == ["HIGH", "MID", "LOW"]
    assert all(g.enough_samples for g in ranked)


# --- 护栏 ------------------------------------------------------------------

def test_validate_dashboard_clean():
    recs = [_rec(f"r{i}", 100 + i) for i in range(6)]
    d = build_dashboard(recs, account_id="a1", platform=_TK, age_hours=24.0,
                         metric=MetricField.VIEWS, generated_at=_T)
    assert validate_dashboard(d) == []


def _dash_with(groups: list[PerformanceGroupStat], *, median=9000.0, min_samples=5):
    return PerformanceDashboard(
        account_id="a1", platform=_TK, generated_at=_T, age_hours=24.0,
        metric=MetricField.VIEWS,
        baseline=AccountBaselineEntry(age_hours=24.0, metric=MetricField.VIEWS,
                                       median=median, sample_count=20),
        min_samples=min_samples, group_stats=groups,
    )


def test_validate_catches_enough_samples_lie():
    # enough_samples=True 但 count=3 < min=5 → 不一致
    g = PerformanceGroupStat(dimension=GroupDimension.TEMPLATE, value="t",
                              age_hours=24.0, metric=MetricField.VIEWS,
                              sample_count=3, median_relative=1.1, enough_samples=True)
    kinds = {i.kind for i in validate_dashboard(_dash_with([g]))}
    assert DashboardIssueKind.ENOUGH_SAMPLES_INCONSISTENT in kinds


def test_validate_catches_median_without_samples():
    g = PerformanceGroupStat(dimension=GroupDimension.TEMPLATE, value="t",
                              age_hours=24.0, metric=MetricField.VIEWS,
                              sample_count=0, median_relative=1.1, enough_samples=False)
    kinds = {i.kind for i in validate_dashboard(_dash_with([g]))}
    assert DashboardIssueKind.MEDIAN_WITHOUT_SAMPLES in kinds


def test_cross_account_records_guard():
    recs = [_rec("a", 100), _rec("x", 200, acct="other"),
            _rec("y", 300, acct="a1")]
    issues = validate_records_single_account(recs, account_id="a1", platform=_TK)
    assert len(issues) == 1
    assert issues[0].kind is DashboardIssueKind.CROSS_ACCOUNT_RECORD
    assert issues[0].ref == "x"
