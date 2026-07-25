"""VF-603 学习信号 domain 测试：Spearman + 关联非因果 + 账号内相对 + 样本不足 + null≠0。"""

from __future__ import annotations

from datetime import UTC, datetime

from videoforge_contracts import (
    LearningReport,
    LearningSignalResult,
    MetricField,
    PerformanceFeatures,
    PerformanceSnapshot,
    PublishPlatform,
    SignalDirection,
    SignalKind,
    VideoPerformanceRecord,
)
from videoforge_domain import (
    LearningIssueKind,
    analyze_signal,
    build_learning_report,
    signal_value,
    significant_signals,
    spearman_correlation,
    validate_learning_report,
)

_T = datetime(2026, 7, 26, tzinfo=UTC)
_TK = PublishPlatform.TIKTOK


def _rec(
    rid, views, *, qa=None, edits=None, selected=None, music=None, hotness=None, acct="a1"
) -> VideoPerformanceRecord:
    f = PerformanceFeatures(
        qa_warning_count=qa,
        manual_edit_count=edits,
        human_selected=selected,
        has_music=music,
        trend_hotness_at_publish=hotness,
    )
    snaps = (
        [
            PerformanceSnapshot(
                id="s",
                platform=_TK,
                platform_post_id="p",
                account_id=acct,
                observed_at=_T,
                age_hours=24.0,
                views=views,
                source_confidence=1.0,
            )
        ]
        if views is not None
        else []
    )
    return VideoPerformanceRecord(
        id=rid, account_id=acct, platform=_TK, published_at=_T, features=f, snapshots=snaps
    )


# --- Spearman ---------------------------------------------------------------


def test_spearman_perfect_and_degenerate():
    assert spearman_correlation([(i, i) for i in range(5)]) == 1.0
    assert spearman_correlation([(i, -i) for i in range(5)]) == -1.0
    assert spearman_correlation([]) is None
    assert spearman_correlation([(1.0, 2.0)]) is None  # n<2
    assert spearman_correlation([(5.0, 1.0), (5.0, 2.0)]) is None  # x 零方差
    assert spearman_correlation([(1.0, 3.0), (2.0, 3.0)]) is None  # y 零方差


def test_spearman_ties_bounded_and_signed():
    corr = spearman_correlation([(1.0, 1.0), (1.0, 3.0), (2.0, 2.0), (2.0, 4.0)])
    assert corr is not None and -1.0 <= corr <= 1.0
    # 反转结局符号翻转
    a = spearman_correlation([(1, 10), (2, 20), (3, 15), (4, 25), (5, 30)])
    b = spearman_correlation([(1, -10), (2, -20), (3, -15), (4, -25), (5, -30)])
    assert a is not None and b is not None and abs(a + b) < 1e-9


# --- 信号取值 --------------------------------------------------------------


def test_signal_value_extraction_and_null():
    f = PerformanceFeatures(qa_warning_count=3, human_selected=True, has_music=False)
    assert signal_value(SignalKind.QA_WARNING_COUNT, f) == 3.0
    assert signal_value(SignalKind.HUMAN_SELECTED, f) == 1.0
    assert signal_value(SignalKind.HAS_MUSIC, f) == 0.0
    assert signal_value(SignalKind.MANUAL_EDIT_COUNT, f) is None  # 缺失
    assert signal_value(SignalKind.TREND_HOTNESS, PerformanceFeatures()) is None


# --- analyze_signal ---------------------------------------------------------


def test_negative_association_and_association_only():
    # QA 越多 → views 越少（完美单调递减）→ corr=-1, NEGATIVE
    recs = [_rec(f"r{i}", 1000 - 100 * i, qa=i) for i in range(10)]
    res = analyze_signal(
        recs,
        signal=SignalKind.QA_WARNING_COUNT,
        baseline_median=550.0,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        min_samples=8,
    )
    assert res.correlation == -1.0
    assert res.direction is SignalDirection.NEGATIVE
    assert res.association_only is True  # 关联非因果（恒 True）
    assert "关联非因果" in res.note


def test_small_sample_is_insufficient_no_direction():
    recs = [_rec(f"r{i}", 100 + 50 * i, qa=i) for i in range(3)]
    res = analyze_signal(
        recs,
        signal=SignalKind.QA_WARNING_COUNT,
        baseline_median=150.0,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        min_samples=8,
    )
    assert res.enough_samples is False
    assert res.direction is SignalDirection.INSUFFICIENT


def test_null_pairs_excluded_never_zero():
    # 8 有效对 + 1 空 views + 1 空信号 → sample_count 8（空对排除，不当 0）
    recs = [_rec(f"r{i}", 100 + 50 * i, qa=i) for i in range(8)]
    recs += [_rec("nv", None, qa=3), _rec("nq", 500, qa=None)]
    res = analyze_signal(
        recs,
        signal=SignalKind.QA_WARNING_COUNT,
        baseline_median=250.0,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        min_samples=8,
    )
    assert res.sample_count == 8


def test_boolean_signal_buckets_yes_no():
    recs = [_rec(f"y{i}", 800 + i, selected=True) for i in range(5)] + [
        _rec(f"n{i}", 200 + i, selected=False) for i in range(5)
    ]
    res = analyze_signal(
        recs,
        signal=SignalKind.HUMAN_SELECTED,
        baseline_median=500.0,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        min_samples=3,
    )
    labels = {b.label for b in res.buckets}
    assert labels == {"是", "否"}
    yes = next(b for b in res.buckets if b.label == "是")
    no = next(b for b in res.buckets if b.label == "否")
    assert yes.median_relative > no.median_relative  # 选中的相对更高


def test_numeric_signal_buckets_terciles():
    recs = [_rec(f"r{i}", 100 + 10 * i, qa=i) for i in range(9)]
    res = analyze_signal(
        recs,
        signal=SignalKind.QA_WARNING_COUNT,
        baseline_median=140.0,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        min_samples=3,
    )
    assert {b.label for b in res.buckets} == {"低", "中", "高"}


# --- report / significant / 账号内 -----------------------------------------


def test_build_report_is_account_scoped():
    a = [_rec(f"a{i}", 100 + 50 * i, qa=i) for i in range(8)]
    b = [_rec(f"b{i}", 9999, qa=0, acct="b1") for i in range(8)]
    rep = build_learning_report(
        a + b,
        account_id="a1",
        platform=_TK,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        generated_at=_T,
        min_samples=8,
    )
    qa = next(s for s in rep.signals if s.signal is SignalKind.QA_WARNING_COUNT)
    assert qa.sample_count == 8  # b1 记录不混入
    assert validate_learning_report(rep) == []


def test_significant_signals_only_directional_and_association():
    recs = [_rec(f"r{i}", 1000 - 100 * i, qa=i, hotness=float(i)) for i in range(10)]
    rep = build_learning_report(
        recs,
        account_id="a1",
        platform=_TK,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        generated_at=_T,
        min_samples=8,
    )
    sig = significant_signals(rep)
    assert all(s.direction in (SignalDirection.POSITIVE, SignalDirection.NEGATIVE) for s in sig)
    assert all(s.enough_samples and s.association_only for s in sig)
    # 降序 |corr|
    corrs = [abs(s.correlation) for s in sig]
    assert corrs == sorted(corrs, reverse=True)


# --- 护栏 ------------------------------------------------------------------


def _result(**over) -> LearningSignalResult:
    base = dict(
        signal=SignalKind.QA_WARNING_COUNT,
        metric=MetricField.VIEWS,
        age_hours=24.0,
        correlation=0.5,
        direction=SignalDirection.POSITIVE,
        sample_count=10,
        enough_samples=True,
    )
    base.update(over)
    return LearningSignalResult(**base)


def _report(results) -> LearningReport:
    return LearningReport(
        account_id="a1",
        platform=_TK,
        generated_at=_T,
        age_hours=24.0,
        metric=MetricField.VIEWS,
        min_samples=8,
        signals=results,
    )


def test_validate_catches_enough_samples_lie():
    r = _result(enough_samples=True, sample_count=2)  # 2 < min 8
    kinds = {i.kind for i in validate_learning_report(_report([r]))}
    assert LearningIssueKind.ENOUGH_SAMPLES_INCONSISTENT in kinds


def test_validate_catches_lens_mismatch():
    r = _result(metric=MetricField.LIKES)  # 报告是 VIEWS
    kinds = {i.kind for i in validate_learning_report(_report([r]))}
    assert LearningIssueKind.SIGNAL_LENS_MISMATCH in kinds
