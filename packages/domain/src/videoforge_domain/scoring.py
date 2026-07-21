"""热度评分聚合（docs/modules/40 §5）。

权重来自 HotScoreWeights 模板对象，不写死在代码——只有公式结构（哪些是负向）
在此。给定子分数与权重，hot_score 完全确定、可重放（40 §10）。
"""

import math

from videoforge_contracts import HotScoreWeights, TrendSubScores


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def normalize_rate(raw: float, *, scale: float) -> float:
    """无界原始增速/加速度 → [0,1] 饱和映射（tanh）。

    scale 是参考量纲（同 cohort 的典型增速）；负原始值（下降/减速）→ 0，
    其贡献由 decay 子分数承载。真实系统应用同 cohort robust z-score（40 §3.2），
    此处提供确定性可重放的近似。
    """
    if scale <= 0:
        return 0.0
    return max(0.0, math.tanh(raw / scale))


def hot_score(
    sub_scores: TrendSubScores,
    weights: HotScoreWeights,
    *,
    source_confidence: float,
) -> float:
    """raw 加权和过 sigmoid，再乘 source_confidence（40 §5）。

    saturation 与 decay 为负向权重。结果 [0,1]。
    """
    raw = (
        weights.velocity * sub_scores.velocity
        + weights.acceleration * sub_scores.acceleration
        + weights.engagement_efficiency * sub_scores.engagement_efficiency
        + weights.cross_platform_score * sub_scores.cross_platform_score
        + weights.topic_fit * sub_scores.topic_fit
        + weights.novelty * sub_scores.novelty
        + weights.source_quality * sub_scores.source_quality
        - weights.saturation * sub_scores.saturation
        - weights.decay * sub_scores.decay
    )
    return sigmoid(raw) * _clamp01(source_confidence)
