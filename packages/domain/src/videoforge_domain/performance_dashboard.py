"""效果看板 domain（docs/modules/44 §11 归因）。纯函数、确定性、可复现。

把已发布视频按 **模板/Hook/创建模式/时长/语言/发布时间** 分组，用**账号内相对指标**
（`指标/账号基线中位数`）做**可解释统计和分桶**。

红线：
- **账号内相对**：`build_dashboard` 先按 account_id + platform 过滤，分组统计都相对于**同一账号**
  的基线中位数——绝不跨账号比较绝对播放（§11）。
- **样本不足不排序**：`rank_groups` 只排 `enough_samples` 的组（`sample_count ≥ min_samples`）；
  低于阈值的组 `insufficient_sample_groups` 只报不排（§11 "有足够样本后再做排序"）。
- **null 语义（承接 VF-601）**：缺失指标(None)从基线与分组聚合中**排除，绝不当 0**——
  基线中位数、组内相对值都只用非空样本。
- **可解释**：只有中位数/分位数(线性插值)/计数，确定性、可复现，无黑盒模型（§11）。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    AccountBaseline,
    AccountBaselineEntry,
    GroupDimension,
    MetricField,
    PerformanceDashboard,
    PerformanceFeatures,
    PerformanceGroupStat,
    PublishPlatform,
    VideoPerformanceRecord,
)
from videoforge_domain.performance import relative_to_baseline

# §11 "有足够样本后再做排序"——低于此样本数的分组不参与排序，只报为低置信。
MIN_SAMPLES_FOR_CONFIDENCE = 5

# 时长分桶（毫秒；[lo, hi)，hi=None 表示 +∞）。
DURATION_BUCKETS: tuple[tuple[int, int | None, str], ...] = (
    (0, 30_000, "0-30s"),
    (30_000, 60_000, "30-60s"),
    (60_000, 90_000, "60-90s"),
    (90_000, None, "90s+"),
)

# MetricField → PerformanceSnapshot 属性名。
_METRIC_ATTR: dict[MetricField, str] = {
    MetricField.VIEWS: "views",
    MetricField.WATCH_TIME: "watch_time_ms",
    MetricField.AVG_WATCH_TIME: "avg_watch_time_ms",
    MetricField.COMPLETION_RATE: "completion_rate",
    MetricField.LIKES: "likes",
    MetricField.COMMENTS: "comments",
    MetricField.SHARES: "shares",
    MetricField.SAVES: "saves",
    MetricField.FOLLOWS: "follows",
    MetricField.IMPRESSIONS: "impressions",
    MetricField.CLICK_THROUGH_RATE: "click_through_rate",
}


# --- 统计原语（确定性，可复现）---------------------------------------------

def percentile(sorted_values: list[float], q: float) -> float | None:
    """线性插值分位数（type-7，numpy 默认）。q ∈ [0,1]。空 → None；单元素 → 该值。"""
    if not sorted_values:
        return None
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    h = (n - 1) * q
    lo = int(h)
    hi = min(lo + 1, n - 1)
    return sorted_values[lo] + (h - lo) * (sorted_values[hi] - sorted_values[lo])


def _stats(values: list[float]) -> tuple[float | None, float | None, float | None, int]:
    """(median, p25, p75, count)。values 已是非空样本（None 已在上游排除）。"""
    s = sorted(values)
    return percentile(s, 0.5), percentile(s, 0.25), percentile(s, 0.75), len(s)


# --- 取值 / 相对指标（null-aware）------------------------------------------

def metric_value_at_age(
    record: VideoPerformanceRecord, age_hours: float, metric: MetricField
) -> float | None:
    """记录在某年龄点的某指标值；无该年龄快照或指标缺失 → None。多个同龄快照取最新观测。"""
    attr = _METRIC_ATTR[metric]
    matches = [s for s in record.snapshots if s.age_hours == age_hours]
    if not matches:
        return None
    snap = max(matches, key=lambda s: s.observed_at)
    return getattr(snap, attr)


def relative_value(
    record: VideoPerformanceRecord,
    baseline_median: float | None,
    age_hours: float,
    metric: MetricField,
) -> float | None:
    """账号内相对指标：`指标/账号基线中位数`。指标缺失或基线为空/0 → None（绝不当 0）。"""
    return relative_to_baseline(
        metric_value_at_age(record, age_hours, metric), baseline_median
    )


# --- 分桶 -------------------------------------------------------------------

def duration_bucket(duration_ms: int | None) -> str | None:
    if duration_ms is None:
        return None
    for lo, hi, label in DURATION_BUCKETS:
        if duration_ms >= lo and (hi is None or duration_ms < hi):
            return label
    return None


def publish_daypart(hour: int | None) -> str | None:
    if hour is None:
        return None
    if 0 <= hour < 6:
        return "夜间(0-6)"
    if 6 <= hour < 12:
        return "上午(6-12)"
    if 12 <= hour < 18:
        return "下午(12-18)"
    return "晚间(18-24)"


def bucket_for(dimension: GroupDimension, features: PerformanceFeatures) -> str | None:
    """记录在某维度上的分组值；该特征缺失(None) → None（该视频不计入此维度分组）。"""
    if dimension is GroupDimension.TEMPLATE:
        return features.template_id
    if dimension is GroupDimension.HOOK:
        return features.hook_kind
    if dimension is GroupDimension.CREATION_MODE:
        return features.creation_mode.value if features.creation_mode else None
    if dimension is GroupDimension.DURATION_BUCKET:
        return duration_bucket(features.duration_ms)
    if dimension is GroupDimension.LANGUAGE:
        return features.language
    if dimension is GroupDimension.PUBLISH_DAYPART:
        return publish_daypart(features.publish_hour)
    return None


# --- 基线 -------------------------------------------------------------------

def compute_account_baseline_entry(
    records: list[VideoPerformanceRecord], age_hours: float, metric: MetricField
) -> AccountBaselineEntry:
    """账号在 (age, metric) 的基线：只用**非空**指标样本（null 排除，绝不当 0）。"""
    values = [
        v for r in records
        if (v := metric_value_at_age(r, age_hours, metric)) is not None
    ]
    median, p25, p75, count = _stats(values)
    return AccountBaselineEntry(
        age_hours=age_hours, metric=metric,
        median=median, p25=p25, p75=p75, sample_count=count,
    )


def build_account_baseline(
    records: list[VideoPerformanceRecord],
    *,
    account_id: str,
    platform: PublishPlatform,
    generated_at: datetime,
    ages_hours: list[float],
    metrics: list[MetricField],
) -> AccountBaseline:
    """某账号的多 age×metric 基线。按 account_id + platform 过滤（账号内，绝不跨账号）。"""
    mine = [r for r in records if r.account_id == account_id and r.platform == platform]
    entries = [
        compute_account_baseline_entry(mine, age, m)
        for age in ages_hours for m in metrics
    ]
    return AccountBaseline(
        account_id=account_id, platform=platform,
        generated_at=generated_at, entries=entries,
    )


# --- 看板 -------------------------------------------------------------------

def build_dashboard(
    records: list[VideoPerformanceRecord],
    *,
    account_id: str,
    platform: PublishPlatform,
    age_hours: float,
    metric: MetricField,
    generated_at: datetime,
    min_samples: int = MIN_SAMPLES_FOR_CONFIDENCE,
    dimensions: list[GroupDimension] | None = None,
) -> PerformanceDashboard:
    """构建某账号在 (age, metric) 视角的看板。**账号内**（先过滤 account+platform），分组相对指标，
    每组标 `enough_samples`。确定性：分组按值排序。"""
    dims = dimensions if dimensions is not None else list(GroupDimension)
    mine = [r for r in records if r.account_id == account_id and r.platform == platform]
    baseline = compute_account_baseline_entry(mine, age_hours, metric)
    bmedian = baseline.median

    stats: list[PerformanceGroupStat] = []
    for dim in dims:
        grouped: dict[str, list[float]] = defaultdict(list)
        for r in mine:
            value = bucket_for(dim, r.features)
            if value is None:
                continue
            rel = relative_value(r, bmedian, age_hours, metric)
            if rel is not None:  # null 排除，绝不当 0
                grouped[value].append(rel)
            else:
                grouped.setdefault(value, [])  # 该维度有此视频但相对值不可用 → count 0
        for value in sorted(grouped):
            median, p25, p75, count = _stats(grouped[value])
            stats.append(PerformanceGroupStat(
                dimension=dim, value=value, age_hours=age_hours, metric=metric,
                sample_count=count, median_relative=median,
                p25_relative=p25, p75_relative=p75,
                enough_samples=count >= min_samples,
            ))

    return PerformanceDashboard(
        account_id=account_id, platform=platform, generated_at=generated_at,
        age_hours=age_hours, metric=metric, baseline=baseline,
        min_samples=min_samples, group_stats=stats,
    )


def rank_groups(
    dashboard: PerformanceDashboard, dimension: GroupDimension | None = None
) -> list[PerformanceGroupStat]:
    """按相对表现降序排序——**只排 enough_samples 的组**（样本不足绝不排序，§11 红线）。
    确定性 tie-break：维度名 → 值。"""
    eligible = [
        g for g in dashboard.group_stats
        if g.enough_samples and g.median_relative is not None
        and (dimension is None or g.dimension is dimension)
    ]
    return sorted(
        eligible,
        key=lambda g: (-g.median_relative, g.dimension.value, g.value),
    )


def insufficient_sample_groups(
    dashboard: PerformanceDashboard,
) -> list[PerformanceGroupStat]:
    """样本不足（低置信、不参与排序）的分组。"""
    return [g for g in dashboard.group_stats if not g.enough_samples]


# --- 护栏 -------------------------------------------------------------------

class DashboardIssueKind(StrEnum):
    ENOUGH_SAMPLES_INCONSISTENT = "ENOUGH_SAMPLES_INCONSISTENT"  # enough_samples 与阈值不符
    RELATIVE_WITHOUT_BASELINE = "RELATIVE_WITHOUT_BASELINE"  # 有相对值却无账号基线中位数
    MEDIAN_WITHOUT_SAMPLES = "MEDIAN_WITHOUT_SAMPLES"  # 有 median_relative 却 sample_count=0
    CROSS_ACCOUNT_RECORD = "CROSS_ACCOUNT_RECORD"  # 记录不属于目标账号/平台（跨账号污染）


@dataclass(frozen=True)
class DashboardIssue:
    kind: DashboardIssueKind
    ref: str
    detail: str


def validate_dashboard(dashboard: PerformanceDashboard) -> list[DashboardIssue]:
    """看板一致性护栏——hand-built 看板不能谎报置信度/相对值。"""
    issues: list[DashboardIssue] = []
    has_baseline = dashboard.baseline.median is not None and dashboard.baseline.median != 0
    for g in dashboard.group_stats:
        ref = f"{g.dimension.value}:{g.value}"
        if g.enough_samples != (g.sample_count >= dashboard.min_samples):
            issues.append(DashboardIssue(
                DashboardIssueKind.ENOUGH_SAMPLES_INCONSISTENT, ref,
                f"enough_samples={g.enough_samples} 但 count={g.sample_count} "
                f"min={dashboard.min_samples}"))
        if g.median_relative is not None and not has_baseline:
            issues.append(DashboardIssue(
                DashboardIssueKind.RELATIVE_WITHOUT_BASELINE, ref,
                "median_relative 非空但账号无基线中位数"))
        if g.median_relative is not None and g.sample_count == 0:
            issues.append(DashboardIssue(
                DashboardIssueKind.MEDIAN_WITHOUT_SAMPLES, ref,
                "median_relative 非空但 sample_count=0"))
    return issues


def validate_records_single_account(
    records: list[VideoPerformanceRecord],
    *,
    account_id: str,
    platform: PublishPlatform,
) -> list[DashboardIssue]:
    """跨账号污染护栏：所有记录必须属于同一目标账号 + 平台（§11 绝不跨账号比较）。"""
    issues: list[DashboardIssue] = []
    for r in records:
        if r.account_id != account_id or r.platform != platform:
            issues.append(DashboardIssue(
                DashboardIssueKind.CROSS_ACCOUNT_RECORD, r.id,
                f"记录 account={r.account_id}/{r.platform.value} "
                f"≠ 目标 {account_id}/{platform.value}"))
    return issues


def is_valid_dashboard(dashboard: PerformanceDashboard) -> bool:
    return not validate_dashboard(dashboard)
