"""VF-604 排序器校准 domain 测试：离线评估门 + 无全量上线 + 探索流量上限 + 有界权重 + null≠0。"""

from __future__ import annotations

from datetime import UTC, datetime

from videoforge_contracts import (
    CalibrationDecision,
    CalibrationProposal,
    RankerKind,
    RankerWeights,
    RankingEvalResult,
    RankingSample,
)
from videoforge_domain import (
    CalibrationIssueKind,
    decide_calibration,
    evaluate_ranking,
    propose_calibration,
    score_item,
    validate_calibration_proposal,
)

_T = datetime(2026, 7, 26, tzinfo=UTC)
_HL = RankerKind.HIGHLIGHT


def _w(version="v1", **coeffs) -> RankerWeights:
    return RankerWeights(
        ranker_kind=_HL, template_version=version, coefficients=coeffs or {"a": 1.0, "b": 0.1}
    )


def _samples(n=24, *, drive="b"):
    # 结局完全由 drive 特征驱动；另一特征反相关
    out = []
    for i in range(n):
        feats = (
            {"a": float(n - i), "b": float(i)}
            if drive == "b"
            else {"a": float(i), "b": float(n - i)}
        )
        out.append(RankingSample(item_id=f"i{i}", features=feats, relative_outcome=float(i)))
    return out


# --- 打分 ------------------------------------------------------------------


def test_score_item_linear_missing_is_zero():
    w = _w(a=2.0, b=3.0)
    assert score_item(w, {"a": 1.0, "b": 1.0}) == 5.0
    assert score_item(w, {"a": 1.0}) == 2.0  # 缺失 b → 0 贡献
    assert score_item(w, {}) == 0.0


# --- 离线评估 --------------------------------------------------------------


def test_evaluate_ranking_corr_and_hit_rate():
    w = _w(a=0.0, b=1.0)  # 只看 b，而结局=b → 完美排序
    res = evaluate_ranking(_samples(24, drive="b"), w, min_samples=20)
    assert res.rank_correlation == 1.0
    assert res.top_k_hit_rate == 1.0  # 预测 top3 == 真实 top3
    assert res.sample_count == 24 and res.enough_samples is True


def test_evaluate_ranking_null_outcome_excluded():
    s = _samples(24) + [
        RankingSample(item_id="nx", features={"a": 1.0, "b": 1.0}, relative_outcome=None)
    ]
    res = evaluate_ranking(s, _w(), min_samples=20)
    assert res.sample_count == 24  # null 结局排除，不当 0


def test_evaluate_empty_metrics_none():
    res = evaluate_ranking([], _w(), min_samples=20)
    assert res.rank_correlation is None and res.top_k_hit_rate is None
    assert res.sample_count == 0 and res.enough_samples is False


# --- 有界校准 --------------------------------------------------------------


def test_propose_calibration_bounded_and_directional():
    cur = _w("v1", good=1.0, bad=1.0)
    # good 与结局正相关 → ↑；bad 反相关 → ↓；各 ≤ ±25%
    samples = [
        RankingSample(
            item_id=f"i{i}",
            features={"good": float(i), "bad": float(24 - i)},
            relative_outcome=float(i),
        )
        for i in range(24)
    ]
    cand = propose_calibration(cur, samples, step=0.2, max_rel_change=0.25)
    assert cand.coefficients["good"] > 1.0 and cand.coefficients["good"] <= 1.25
    assert cand.coefficients["bad"] < 1.0 and cand.coefficients["bad"] >= 0.75
    assert all(v >= 0 for v in cand.coefficients.values())
    assert cand.template_version == "v1+cal"


def test_propose_calibration_stays_non_negative():
    cur = _w("v1", x=0.05)
    samples = [
        RankingSample(item_id=f"i{i}", features={"x": float(24 - i)}, relative_outcome=float(i))
        for i in range(24)
    ]
    cand = propose_calibration(cur, samples, step=0.9, max_rel_change=2.0)
    assert cand.coefficients["x"] >= 0.0


# --- 决策：离线门 + 少量探索（红线）----------------------------------------


def test_decide_explore_when_candidate_better():
    cur = _w("v1", a=1.0, b=0.0)  # 只看 a，但结局=b → 差
    cand = _w("v2", a=0.0, b=1.0)  # 只看 b → 好
    prop = decide_calibration(
        cur,
        cand,
        _samples(24, drive="b"),
        generated_at=_T,
        min_samples=20,
        min_improvement=0.05,
        exploration_fraction=0.1,
    )
    assert prop.decision is CalibrationDecision.EXPLORE
    assert prop.promotable is True and prop.improvement > 0
    assert 0 < prop.exploration_fraction <= 0.2
    assert validate_calibration_proposal(prop) == []


def test_decide_keep_current_when_not_better():
    cur = _w("v1", a=0.0, b=1.0)  # 已经最优
    cand = _w("v2", a=1.0, b=0.0)  # 更差
    prop = decide_calibration(
        cur, cand, _samples(24, drive="b"), generated_at=_T, min_samples=20, min_improvement=0.05
    )
    assert prop.decision is CalibrationDecision.KEEP_CURRENT
    assert prop.promotable is False and prop.exploration_fraction == 0.0


def test_decide_insufficient_samples():
    prop = decide_calibration(_w(), _w("v2"), _samples(5), generated_at=_T, min_samples=20)
    assert prop.decision is CalibrationDecision.INSUFFICIENT_SAMPLES
    assert prop.promotable is False and prop.exploration_fraction == 0.0


def test_exploration_fraction_capped():
    cur = _w("v1", a=1.0, b=0.0)
    cand = _w("v2", a=0.0, b=1.0)
    prop = decide_calibration(
        cur,
        cand,
        _samples(24, drive="b"),
        generated_at=_T,
        min_samples=20,
        min_improvement=0.0,
        exploration_fraction=0.9,
        max_exploration_fraction=0.2,
    )
    assert prop.exploration_fraction == 0.2  # 上限封顶，绝不全量


def test_no_full_rollout_decision_exists():
    # 结构性红线：没有"全量替换"决策值——最强只是 EXPLORE
    assert {d.value for d in CalibrationDecision} == {
        "KEEP_CURRENT",
        "EXPLORE",
        "INSUFFICIENT_SAMPLES",
    }


def test_contract_rejects_inflated_max_exploration():
    # verifier REFUTED 回归：max_exploration_fraction 只能收紧、绝不能放宽到硬上限之上
    ev = RankingEvalResult(
        ranker_kind=_HL,
        template_version="v1",
        top_k=3,
        rank_correlation=0.5,
        sample_count=24,
        enough_samples=True,
    )
    import pytest

    for bad in (
        {"max_exploration_fraction": 1.0, "exploration_fraction": 1.0},
        {"max_exploration_fraction": 0.5, "exploration_fraction": 0.3},
        {"max_exploration_fraction": 0.2, "exploration_fraction": 0.3},
    ):
        with pytest.raises(ValueError):
            CalibrationProposal(
                ranker_kind=_HL,
                current=_w(),
                candidate=_w("v2"),
                current_eval=ev,
                candidate_eval=ev,
                improvement=2.0,
                promotable=True,
                decision=CalibrationDecision.EXPLORE,
                generated_at=_T,
                **bad,
            )


def test_engine_clamps_exploration_against_hard_cap():
    # 即使调用方传 max=1.0/frac=0.9，引擎也把两者钳到硬上限 0.2——绝不全量上线
    cur = _w("v1", a=1.0, b=0.0)
    cand = _w("v2", a=0.0, b=1.0)
    prop = decide_calibration(
        cur,
        cand,
        _samples(24, drive="b"),
        generated_at=_T,
        min_samples=20,
        min_improvement=0.0,
        exploration_fraction=0.9,
        max_exploration_fraction=1.0,
    )
    assert prop.exploration_fraction == 0.2 and prop.max_exploration_fraction == 0.2
    assert validate_calibration_proposal(prop) == []


# --- 护栏 ------------------------------------------------------------------


def test_validate_catches_promotable_without_samples():
    # promotable=True 但样本不足（decision KEEP_CURRENT 合法构造）
    thin_eval = RankingEvalResult(
        ranker_kind=_HL,
        template_version="v1",
        top_k=3,
        rank_correlation=0.5,
        sample_count=3,
        enough_samples=False,
    )
    prop = CalibrationProposal(
        ranker_kind=_HL,
        current=_w(),
        candidate=_w("v2"),
        current_eval=thin_eval,
        candidate_eval=thin_eval,
        improvement=0.1,
        promotable=True,
        decision=CalibrationDecision.KEEP_CURRENT,
        exploration_fraction=0.0,
        generated_at=_T,
    )
    kinds = {i.kind for i in validate_calibration_proposal(prop)}
    assert CalibrationIssueKind.PROMOTABLE_WITHOUT_SAMPLES in kinds
