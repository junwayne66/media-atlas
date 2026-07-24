"""时长拟合合同（docs/modules/43 §8）。

**顺序回退**：目标句超/短 → LLM_REWRITE → TTS_SPEED (0.92-1.08) → BROLL_ADJUST →
TIME_STRETCH（非人脸小幅）→ BEAT_REPLAN；**禁止极端压速**（超自然区间即视为失败，
不允许方案二"硬压到 0.7x"这类）。每句记录 fit_method 与最终伸缩比。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel


class DurationFitStrategy(StrEnum):
    """§8 五步顺序策略。"""

    LLM_REWRITE = "LLM_REWRITE"
    TTS_SPEED = "TTS_SPEED"
    BROLL_ADJUST = "BROLL_ADJUST"
    TIME_STRETCH = "TIME_STRETCH"
    BEAT_REPLAN = "BEAT_REPLAN"


class DurationFitStatus(StrEnum):
    """决策结果状态。"""

    OK_UNCHANGED = "OK_UNCHANGED"  # 已在预算，无需拟合
    OK_FITTED = "OK_FITTED"  # 用某个策略拟合成功
    NEEDS_REVIEW = "NEEDS_REVIEW"  # 需人工，含极端压速被拒
    FAILED = "FAILED"  # 五步都不成立


class DurationFitDecision(ContractModel):
    """一句的拟合决策。fit_method 与 final_ratio 忠实记录（§8 每句必录）。"""

    sentence_id: str = Field(min_length=1)
    estimated_ms: int = Field(ge=0, description="TTS 估算时长（VF-404 estimate）")
    target_ms: int = Field(gt=0)
    fit_method: DurationFitStrategy | None = Field(
        default=None, description="OK_UNCHANGED 时为 None",
    )
    final_ratio: float = Field(
        gt=0.0, description="估算/目标；用于最终伸缩记录",
    )
    status: DurationFitStatus
    rationale: str = Field(min_length=1)
    review_reasons: list[str] = Field(default_factory=list)


class DurationFitPlan(ContractModel):
    """一整个 LocalizationVariant 的拟合计划。"""

    id: str = Field(min_length=1)
    localization_variant_id: str = Field(min_length=1)
    decisions: list[DurationFitDecision] = Field(default_factory=list)
    natural_speed_min: float = Field(default=0.92, gt=0.0, le=1.0)
    natural_speed_max: float = Field(default=1.08, gt=1.0)
    stretch_max_abs_ratio: float = Field(
        default=0.05, ge=0.0, le=0.5,
        description="非人脸时间伸缩绝对幅度（±5%）",
    )
    created_at: datetime

    @model_validator(mode="after")
    def _check_unique_and_bounds(self) -> "DurationFitPlan":
        if self.natural_speed_min >= self.natural_speed_max:
            raise ValueError(
                f"natural_speed_min({self.natural_speed_min}) 必须 < "
                f"max({self.natural_speed_max})"
            )
        seen: set[str] = set()
        for d in self.decisions:
            if d.sentence_id in seen:
                raise ValueError(
                    f"重复的 sentence_id: {d.sentence_id!r}"
                )
            seen.add(d.sentence_id)
        return self
