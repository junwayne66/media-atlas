"""可解释理由码推导（docs/modules/40 §7 示例，§10：Top-20 需 ≥2 条）。

纯函数：给定子分数与阶段，产出稳定排序的理由码列表，供人审与排序解释。
"""

from videoforge_contracts import TrendStage, TrendSubScores

# (属性, 阈值, 码)；按声明顺序即输出顺序
_RULES: list[tuple[str, float, str]] = [
    ("acceleration", 0.5, "HIGH_ACCELERATION"),
    ("velocity", 0.5, "HIGH_VELOCITY"),
    ("cross_platform_score", 0.5, "CROSS_PLATFORM"),
    ("engagement_efficiency", 0.5, "HIGH_ENGAGEMENT"),
    ("topic_fit", 0.5, "STRONG_TOPIC_FIT"),
    ("novelty", 0.6, "NOVEL_ANGLE"),
    ("source_quality", 0.6, "QUALITY_SOURCE"),
    ("saturation", 0.6, "HIGH_SATURATION"),
    ("decay", 0.5, "DECAYING_SIGNAL"),
]

_STAGE_CODES: dict[TrendStage, str] = {
    TrendStage.EMERGING: "EARLY_STAGE",
    TrendStage.SATURATED: "SUPPLY_SATURATED",
    TrendStage.DECAYING: "PAST_PEAK",
}


def derive_reason_codes(sub_scores: TrendSubScores, stage: TrendStage) -> list[str]:
    codes = [code for attr, threshold, code in _RULES if getattr(sub_scores, attr) >= threshold]
    stage_code = _STAGE_CODES.get(stage)
    if stage_code is not None:
        codes.append(stage_code)
    return codes
