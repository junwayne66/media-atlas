"""排序器校准 domain（docs/modules/44 §11 末：先离线评估再少量探索）。纯函数、确定性、可复现。

用历史 (特征, 账号内相对结局) 样本对**排序器权重**做**离线评估**与**有界校准**，
最强动作只是把候选放到**受限探索流量**——绝不一步全量上线黑盒排序器。

红线：
- **离线评估门**：`evaluate_ranking` 用 Spearman 秩相关 + Top-k 命中衡量一组权重的排序质量；
  候选只有以足够样本超过当前一个 margin 才 `promotable`。
- **无全量自动上线**：`decide_calibration` 最强返回 EXPLORE（候选获 `exploration_fraction`
  ≤ 上限的探索流量），无"全量替换"路径。
- **有界可解释权重**：`propose_calibration` 按各特征与结局的秩相关做**有界微调**（每系数相对变化
  ≤ max_rel_change、结果 ≥0），模板版本化、可审计——非训练黑盒。
- **样本不足不校准**：不足 → INSUFFICIENT_SAMPLES。
- **null≠0**：相对结局为 None 的样本不计入评估/校准。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    CalibrationDecision,
    CalibrationProposal,
    RankerWeights,
    RankingEvalResult,
    RankingSample,
)
from videoforge_contracts.calibration import MAX_EXPLORATION_FRACTION
from videoforge_domain.learning_signals import spearman_correlation

DEFAULT_TOP_K = 3
MIN_SAMPLES_FOR_CALIBRATION = 20  # §11 "样本足够"（呼应 Trusted Template 的 ≥20 门槛）
DEFAULT_MIN_IMPROVEMENT = 0.05  # 候选秩相关须至少超当前 0.05 才 promotable
DEFAULT_STEP = 0.2  # 校准微调步长
DEFAULT_MAX_REL_CHANGE = 0.25  # 每系数单次相对变化上限（有界）


# --- 打分 -------------------------------------------------------------------


def score_item(weights: RankerWeights, features: dict[str, float]) -> float:
    """线性打分 Σ 系数·特征。缺失特征按 0（中性）计入——可解释线性排序。"""
    return sum(coef * features.get(name, 0.0) for name, coef in weights.coefficients.items())


def _top_k_ids(scored: list[tuple[str, float]], k: int) -> list[str]:
    """按分数降序取前 k 的 item_id；tie-break item_id 升序（确定性）。"""
    ordered = sorted(scored, key=lambda p: (-p[1], p[0]))
    return [item_id for item_id, _ in ordered[:k]]


# --- 离线评估 ---------------------------------------------------------------


def evaluate_ranking(
    samples: list[RankingSample],
    weights: RankerWeights,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_samples: int = MIN_SAMPLES_FOR_CALIBRATION,
) -> RankingEvalResult:
    """一组权重在历史样本上的离线排序质量。**只用相对结局非空的样本**（null≠0）。"""
    usable = [s for s in samples if s.relative_outcome is not None]
    n = len(usable)

    pairs = [(score_item(weights, s.features), s.relative_outcome) for s in usable]
    corr = spearman_correlation(pairs)

    hit_rate: float | None = None
    if n > 0:
        k = min(top_k, n)
        pred_top = set(
            _top_k_ids([(s.item_id, score_item(weights, s.features)) for s in usable], k)
        )
        true_top = set(_top_k_ids([(s.item_id, s.relative_outcome) for s in usable], k))
        hit_rate = len(pred_top & true_top) / k

    return RankingEvalResult(
        ranker_kind=weights.ranker_kind,
        template_version=weights.template_version,
        rank_correlation=corr,
        top_k=top_k,
        top_k_hit_rate=hit_rate,
        sample_count=n,
        enough_samples=n >= min_samples,
    )


# --- 有界校准（可解释微调）--------------------------------------------------


def propose_calibration(
    current: RankerWeights,
    samples: list[RankingSample],
    *,
    step: float = DEFAULT_STEP,
    max_rel_change: float = DEFAULT_MAX_REL_CHANGE,
    version_suffix: str = "+cal",
) -> RankerWeights:
    """按各特征与相对结局的秩相关做**有界微调**：正相关↑、负相关↓，每系数相对变化 ≤ max_rel_change、
    结果 ≥0。可解释、可审计，模板版本追加 suffix。null 结局样本不参与。"""
    usable = [s for s in samples if s.relative_outcome is not None]
    new_coeffs: dict[str, float] = {}
    for name, coef in current.coefficients.items():
        pairs = [(s.features[name], s.relative_outcome) for s in usable if name in s.features]
        corr = spearman_correlation(pairs) or 0.0
        factor = 1.0 + step * corr
        lo = coef * (1.0 - max_rel_change)
        hi = coef * (1.0 + max_rel_change)
        new_coeffs[name] = max(0.0, min(max(coef * factor, lo), hi))
    return RankerWeights(
        ranker_kind=current.ranker_kind,
        template_version=f"{current.template_version}{version_suffix}",
        coefficients=new_coeffs,
    )


# --- 决策：离线评估门 + 少量探索 -------------------------------------------


def decide_calibration(
    current: RankerWeights,
    candidate: RankerWeights,
    samples: list[RankingSample],
    *,
    generated_at: datetime,
    top_k: int = DEFAULT_TOP_K,
    min_samples: int = MIN_SAMPLES_FOR_CALIBRATION,
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
    exploration_fraction: float = 0.1,
    max_exploration_fraction: float = MAX_EXPLORATION_FRACTION,
) -> CalibrationProposal:
    """离线评估当前 vs 候选，决定 KEEP_CURRENT / EXPLORE / INSUFFICIENT_SAMPLES。
    **最强动作只是 EXPLORE（受限探索流量），无全量上线。**"""
    cur_eval = evaluate_ranking(samples, current, top_k=top_k, min_samples=min_samples)
    cand_eval = evaluate_ranking(samples, candidate, top_k=top_k, min_samples=min_samples)

    cur_metric = cur_eval.rank_correlation
    cand_metric = cand_eval.rank_correlation
    improvement = (
        (cand_metric - cur_metric) if cur_metric is not None and cand_metric is not None else 0.0
    )

    enough = cur_eval.enough_samples and cand_eval.enough_samples
    promotable = (
        enough
        and cand_metric is not None
        and cur_metric is not None
        and improvement >= min_improvement
    )

    # 硬上限永远赢：调用方声明的 max 只能收紧、绝不能放宽到 MAX_EXPLORATION_FRACTION 之上。
    effective_max = min(max_exploration_fraction, MAX_EXPLORATION_FRACTION)

    if not enough:
        decision = CalibrationDecision.INSUFFICIENT_SAMPLES
        frac = 0.0
    elif promotable:
        decision = CalibrationDecision.EXPLORE
        frac = min(exploration_fraction, effective_max)
    else:
        decision = CalibrationDecision.KEEP_CURRENT
        frac = 0.0

    return CalibrationProposal(
        ranker_kind=current.ranker_kind,
        current=current,
        candidate=candidate,
        current_eval=cur_eval,
        candidate_eval=cand_eval,
        improvement=improvement,
        promotable=promotable,
        decision=decision,
        exploration_fraction=frac,
        max_exploration_fraction=effective_max,
        generated_at=generated_at,
        note=_explain(decision, improvement, cur_eval.sample_count),
    )


def _explain(decision: CalibrationDecision, improvement: float, n: int) -> str:
    if decision is CalibrationDecision.INSUFFICIENT_SAMPLES:
        return f"样本不足（n={n}），不校准"
    if decision is CalibrationDecision.EXPLORE:
        return f"候选离线秩相关 +{improvement:.3f}，进入少量探索（保留探索流量）"
    return f"候选未显著超过当前（Δ={improvement:.3f}），维持当前"


# --- 护栏 -------------------------------------------------------------------


class CalibrationIssueKind(StrEnum):
    EXPLORE_WITHOUT_PROMOTABLE = "EXPLORE_WITHOUT_PROMOTABLE"  # EXPLORE 却不 promotable
    EXPLORATION_EXCEEDS_MAX = "EXPLORATION_EXCEEDS_MAX"  # 探索比例超上限
    PROMOTABLE_WITHOUT_SAMPLES = "PROMOTABLE_WITHOUT_SAMPLES"  # promotable 却样本不足
    NEGATIVE_WEIGHT = "NEGATIVE_WEIGHT"  # 系数为负（合同已拦，纵深）
    RANKER_KIND_MISMATCH = "RANKER_KIND_MISMATCH"  # ranker_kind 不一致（合同已拦，纵深）


@dataclass(frozen=True)
class CalibrationIssue:
    kind: CalibrationIssueKind
    ref: str
    detail: str


def validate_calibration_proposal(proposal: CalibrationProposal) -> list[CalibrationIssue]:
    """校准提案护栏——hand-built 提案不能绕过离线门/探索流量上限（§11 红线）。"""
    issues: list[CalibrationIssue] = []
    ref = proposal.ranker_kind.value

    if proposal.decision is CalibrationDecision.EXPLORE and not proposal.promotable:
        issues.append(
            CalibrationIssue(
                CalibrationIssueKind.EXPLORE_WITHOUT_PROMOTABLE,
                ref,
                "EXPLORE 却 promotable=False（未过离线评估门）",
            )
        )
    # 硬上限（常量）+ 自声明上限，两道都查——防篡改绕过（verifier REFUTED 的漏洞）。
    if (
        proposal.exploration_fraction > proposal.max_exploration_fraction
        or proposal.exploration_fraction > MAX_EXPLORATION_FRACTION
        or proposal.max_exploration_fraction > MAX_EXPLORATION_FRACTION
    ):
        issues.append(
            CalibrationIssue(
                CalibrationIssueKind.EXPLORATION_EXCEEDS_MAX,
                ref,
                f"探索比例 {proposal.exploration_fraction} / 上限 "
                f"{proposal.max_exploration_fraction} 超过硬上限 {MAX_EXPLORATION_FRACTION}",
            )
        )
    if proposal.promotable and not (
        proposal.current_eval.enough_samples and proposal.candidate_eval.enough_samples
    ):
        issues.append(
            CalibrationIssue(
                CalibrationIssueKind.PROMOTABLE_WITHOUT_SAMPLES, ref, "promotable=True 却样本不足"
            )
        )
    for label, w in (("current", proposal.current), ("candidate", proposal.candidate)):
        for name, value in w.coefficients.items():
            if value < 0:
                issues.append(
                    CalibrationIssue(
                        CalibrationIssueKind.NEGATIVE_WEIGHT,
                        f"{ref}:{label}:{name}",
                        f"系数 {value} < 0",
                    )
                )
    if (
        len({proposal.current.ranker_kind, proposal.candidate.ranker_kind, proposal.ranker_kind})
        != 1
    ):
        issues.append(
            CalibrationIssue(CalibrationIssueKind.RANKER_KIND_MISMATCH, ref, "ranker_kind 不一致")
        )
    return issues


def is_valid_calibration_proposal(proposal: CalibrationProposal) -> bool:
    return not validate_calibration_proposal(proposal)
