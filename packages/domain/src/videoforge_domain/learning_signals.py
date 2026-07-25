"""学习信号 domain（docs/modules/44 §11 归因与学习信号）。纯函数、确定性、可复现。

把**过程信号**（人工选择/驳回、QA 警告、修改次数、发布时热度、发布延迟、时长、配乐）与
**账号内相对表现**（承接 VF-602）做**可解释统计关联**——透明的 Spearman 秩相关 + 分桶中位数。

红线：
- **关联非因果**：`association_only` 恒 True；`direction`/`note` 只报"相关"，`significant_signals`
  绝不表述成因果建议（§11：不训练黑盒爆款模型）。
- **可解释**：`spearman_correlation` 是标准秩相关（∈[-1,1]，含并列平均秩），可复现无黑盒。
- **账号内相对**：`build_learning_report` 先按 account_id+platform 过滤；结局用相对指标。
- **样本不足不下结论**：`enough_samples`/`INSUFFICIENT`——不足只报低置信，不给方向。
- **null≠0**：信号或结局缺失的样本对不计入（`(signal, outcome)` 两端都需非空）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    LearningReport,
    LearningSignalResult,
    MetricField,
    PerformanceFeatures,
    PublishPlatform,
    SignalBucketStat,
    SignalDirection,
    SignalKind,
    VideoPerformanceRecord,
)
from videoforge_domain.performance import relative_to_baseline
from videoforge_domain.performance_dashboard import (
    compute_account_baseline_entry,
    metric_value_at_age,
    percentile,
)

# |Spearman| ≥ 此值才判为有方向的关联（否则 NONE）。
DEFAULT_CORR_THRESHOLD = 0.3
# 达到方向性结论所需的最小样本对数。
MIN_SAMPLES_FOR_SIGNAL = 8

# 布尔型信号（分两桶 是/否）；其余按信号值分三桶 低/中/高。
_BOOLEAN_SIGNALS = frozenset(
    {
        SignalKind.HUMAN_SELECTED,
        SignalKind.REJECTED_THEN_REVISED,
        SignalKind.HAS_MUSIC,
    }
)


# --- Spearman 秩相关（透明、可复现）----------------------------------------


def _ranks(values: list[float]) -> list[float]:
    """1-based 平均秩（并列取平均）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 平均秩，1-based
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman_correlation(pairs: list[tuple[float, float]]) -> float | None:
    """Spearman 秩相关 ∈[-1,1]。< 2 对或任一维零方差（全相等）→ None。"""
    n = len(pairs)
    if n < 2:
        return None
    rx = _ranks([p[0] for p in pairs])
    ry = _ranks([p[1] for p in pairs])
    mx = sum(rx) / n
    my = sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n))
    vy = sum((ry[i] - my) ** 2 for i in range(n))
    if vx == 0 or vy == 0:
        return None
    corr = cov / (vx * vy) ** 0.5
    return max(-1.0, min(1.0, corr))  # 数值夹紧到 [-1,1]


# --- 信号取值 ---------------------------------------------------------------


def _bool_to_float(b: bool | None) -> float | None:
    return None if b is None else (1.0 if b else 0.0)


def signal_value(kind: SignalKind, features: PerformanceFeatures) -> float | None:
    """从特征取信号数值（布尔→1.0/0.0）；缺失 → None。"""
    if kind is SignalKind.QA_WARNING_COUNT:
        v: int | float | None = features.qa_warning_count
    elif kind is SignalKind.MANUAL_EDIT_COUNT:
        v = features.manual_edit_count
    elif kind is SignalKind.HUMAN_SELECTED:
        return _bool_to_float(features.human_selected)
    elif kind is SignalKind.REJECTED_THEN_REVISED:
        return _bool_to_float(features.rejected_then_revised)
    elif kind is SignalKind.TREND_HOTNESS:
        v = features.trend_hotness_at_publish
    elif kind is SignalKind.PUBLISH_DELAY:
        v = features.publish_delay_hours
    elif kind is SignalKind.DURATION:
        v = features.duration_ms
    elif kind is SignalKind.HAS_MUSIC:
        return _bool_to_float(features.has_music)
    else:  # pragma: no cover - 穷尽枚举
        return None
    return None if v is None else float(v)


# --- 分桶 -------------------------------------------------------------------


def _bucketize(
    signal: SignalKind, pairs: list[tuple[float, float]], min_samples: int
) -> list[SignalBucketStat]:
    """把 (信号值, 相对结局) 对分桶，报每桶相对结局中位数。布尔→是/否；数值→低/中/高(三分位)。"""
    groups: list[tuple[str, list[float]]] = []
    if signal in _BOOLEAN_SIGNALS:
        no = [rel for sv, rel in pairs if sv == 0.0]
        yes = [rel for sv, rel in pairs if sv == 1.0]
        groups = [("否", no), ("是", yes)]
    else:
        svals = sorted(sv for sv, _ in pairs)
        if svals:
            t1 = percentile(svals, 1 / 3)
            t2 = percentile(svals, 2 / 3)
            low = [rel for sv, rel in pairs if sv <= t1]
            mid = [rel for sv, rel in pairs if t1 < sv <= t2]
            high = [rel for sv, rel in pairs if sv > t2]
            groups = [("低", low), ("中", mid), ("高", high)]

    stats: list[SignalBucketStat] = []
    for label, vals in groups:
        if not vals:
            continue  # 空桶不报
        median = percentile(sorted(vals), 0.5)
        stats.append(
            SignalBucketStat(
                label=label,
                sample_count=len(vals),
                median_relative=median,
                enough_samples=len(vals) >= min_samples,
            )
        )
    return stats


# --- 方向 + 说明 ------------------------------------------------------------


def _direction(correlation: float | None, enough: bool, threshold: float) -> SignalDirection:
    if not enough:
        return SignalDirection.INSUFFICIENT
    if correlation is None:
        return SignalDirection.NONE
    if correlation >= threshold:
        return SignalDirection.POSITIVE
    if correlation <= -threshold:
        return SignalDirection.NEGATIVE
    return SignalDirection.NONE


def _explain(signal: SignalKind, direction: SignalDirection, corr: float | None, n: int) -> str:
    if direction is SignalDirection.INSUFFICIENT:
        return f"{signal.value}：样本不足（n={n}），暂不下结论"
    c = "n/a" if corr is None else f"{corr:.2f}"
    if direction is SignalDirection.POSITIVE:
        return (
            f"{signal.value} 越高，账号内相对表现越高的**相关**（Spearman={c}, n={n}）——关联非因果"
        )
    if direction is SignalDirection.NEGATIVE:
        return (
            f"{signal.value} 越高，账号内相对表现越低的**相关**（Spearman={c}, n={n}）——关联非因果"
        )
    return f"{signal.value}：无明显关联（Spearman={c}, n={n}）"


# --- 单信号分析 -------------------------------------------------------------


def analyze_signal(
    records: list[VideoPerformanceRecord],
    *,
    signal: SignalKind,
    baseline_median: float | None,
    age_hours: float,
    metric: MetricField,
    min_samples: int = MIN_SAMPLES_FOR_SIGNAL,
    corr_threshold: float = DEFAULT_CORR_THRESHOLD,
) -> LearningSignalResult:
    """一个信号 vs 相对结局的关联分析。只用 (信号, 结局) 两端非空的样本对（null≠0）。"""
    pairs: list[tuple[float, float]] = []
    for r in records:
        sv = signal_value(signal, r.features)
        if sv is None:
            continue
        rel = relative_to_baseline(metric_value_at_age(r, age_hours, metric), baseline_median)
        if rel is None:
            continue
        pairs.append((sv, rel))

    n = len(pairs)
    corr = spearman_correlation(pairs)
    enough = n >= min_samples
    direction = _direction(corr, enough, corr_threshold)
    return LearningSignalResult(
        signal=signal,
        metric=metric,
        age_hours=age_hours,
        correlation=corr,
        direction=direction,
        sample_count=n,
        enough_samples=enough,
        buckets=_bucketize(signal, pairs, min_samples),
        note=_explain(signal, direction, corr, n),
    )


def build_learning_report(
    records: list[VideoPerformanceRecord],
    *,
    account_id: str,
    platform: PublishPlatform,
    age_hours: float,
    metric: MetricField,
    generated_at: datetime,
    signals: list[SignalKind] | None = None,
    min_samples: int = MIN_SAMPLES_FOR_SIGNAL,
    corr_threshold: float = DEFAULT_CORR_THRESHOLD,
) -> LearningReport:
    """某账号在 (age, metric) 视角下各信号的关联报告。**账号内**（先过滤 account+platform）。"""
    sigs = signals if signals is not None else list(SignalKind)
    mine = [r for r in records if r.account_id == account_id and r.platform == platform]
    baseline = compute_account_baseline_entry(mine, age_hours, metric)
    results = [
        analyze_signal(
            mine,
            signal=s,
            baseline_median=baseline.median,
            age_hours=age_hours,
            metric=metric,
            min_samples=min_samples,
            corr_threshold=corr_threshold,
        )
        for s in sigs
    ]
    return LearningReport(
        account_id=account_id,
        platform=platform,
        generated_at=generated_at,
        age_hours=age_hours,
        metric=metric,
        min_samples=min_samples,
        signals=results,
    )


def significant_signals(
    report: LearningReport, *, min_abs_correlation: float = DEFAULT_CORR_THRESHOLD
) -> list[LearningSignalResult]:
    """有方向、样本足、|相关| ≥ 阈值的信号，按 |相关| 降序。**仍是关联，绝非因果建议**。"""
    eligible = [
        s
        for s in report.signals
        if s.enough_samples
        and s.correlation is not None
        and abs(s.correlation) >= min_abs_correlation
        and s.direction in (SignalDirection.POSITIVE, SignalDirection.NEGATIVE)
    ]
    return sorted(eligible, key=lambda s: (-abs(s.correlation), s.signal.value))


# --- 护栏 -------------------------------------------------------------------


class LearningIssueKind(StrEnum):
    CAUSAL_CLAIM = "CAUSAL_CLAIM"  # association_only=False（因果越界）
    CORRELATION_OUT_OF_RANGE = "CORRELATION_OUT_OF_RANGE"  # corr ∉ [-1,1]
    DIRECTION_WITHOUT_SAMPLES = "DIRECTION_WITHOUT_SAMPLES"  # 样本不足却给方向
    ENOUGH_SAMPLES_INCONSISTENT = "ENOUGH_SAMPLES_INCONSISTENT"  # enough 与阈值不符
    SIGNAL_LENS_MISMATCH = "SIGNAL_LENS_MISMATCH"  # 信号结果 metric/age 与报告不一致


@dataclass(frozen=True)
class LearningIssue:
    kind: LearningIssueKind
    ref: str
    detail: str


def validate_learning_report(report: LearningReport) -> list[LearningIssue]:
    """学习信号一致性护栏——hand-built 报告不能作因果越界或谎报置信。"""
    issues: list[LearningIssue] = []
    for s in report.signals:
        ref = s.signal.value
        if s.association_only is not True:
            issues.append(
                LearningIssue(
                    LearningIssueKind.CAUSAL_CLAIM,
                    ref,
                    "association_only 必须为 True（关联非因果）",
                )
            )
        if s.correlation is not None and not (-1.0 <= s.correlation <= 1.0):
            issues.append(
                LearningIssue(
                    LearningIssueKind.CORRELATION_OUT_OF_RANGE,
                    ref,
                    f"correlation={s.correlation} ∉ [-1,1]",
                )
            )
        if not s.enough_samples and s.direction in (
            SignalDirection.POSITIVE,
            SignalDirection.NEGATIVE,
        ):
            issues.append(
                LearningIssue(
                    LearningIssueKind.DIRECTION_WITHOUT_SAMPLES,
                    ref,
                    f"样本不足却给方向 {s.direction.value}",
                )
            )
        if s.enough_samples != (s.sample_count >= report.min_samples):
            issues.append(
                LearningIssue(
                    LearningIssueKind.ENOUGH_SAMPLES_INCONSISTENT,
                    ref,
                    f"enough_samples={s.enough_samples} 但 count={s.sample_count} "
                    f"min={report.min_samples}",
                )
            )
        if s.metric != report.metric or s.age_hours != report.age_hours:
            issues.append(
                LearningIssue(
                    LearningIssueKind.SIGNAL_LENS_MISMATCH,
                    ref,
                    f"信号 {s.metric.value}@{s.age_hours} ≠ 报告 "
                    f"{report.metric.value}@{report.age_hours}",
                )
            )
    return issues


def is_valid_learning_report(report: LearningReport) -> bool:
    return not validate_learning_report(report)
