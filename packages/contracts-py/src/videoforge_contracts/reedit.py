"""原片重剪计划合同（docs/modules/42 §4）。

源转录/素材 → 有序 EditOp（KEEP/DELETE/MUTE/SPEED/REFRAME）+ 连续性说明 → ReeditPlan。
SegmentJudgment 是"哪些句段可删"的模型判断（provider 产出、domain 消费），非持久聚合、不注册。
纯域 build_reedit_plan 据判定成计划，validate_reedit_plan 施加 §4.2 连续性/不切句/变速护栏。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import ContinuityRuleKind, EditOpKind, ReframeFollow


class SegmentJudgment(ContractModel):
    """对源转录一个句段的重剪判定（模型判断）。keep_recommended=False 即建议删除。"""

    segment_id: str = Field(min_length=1)
    keep_recommended: bool = True
    is_silence: bool = False
    is_filler: bool = False  # 口头禅/语气词
    is_repeat: bool = False
    is_low_info: bool = False
    note: str | None = None


class ReframeHint(ContractModel):
    """重构图建议（docs/modules/42 §4.1）。"""

    target_aspect_ratio: str = Field(min_length=1, description="如 9:16")
    follow: ReframeFollow = ReframeFollow.CENTER
    safe_area: str | None = None


class EditOp(ContractModel):
    """一次重剪操作，作用于源时间区间（docs/modules/42 §4.1）。"""

    id: str = Field(min_length=1)
    op: EditOpKind
    source_start_ms: int = Field(ge=0)
    source_end_ms: int = Field(ge=0)
    segment_ids: list[str] = Field(default_factory=list, description="覆盖的源转录句段")
    output_order: int | None = Field(default=None, ge=0, description="KEEP 在输出中的次序（重排）")
    reason: str | None = Field(default=None, description="DELETE 原因，如 silence/filler/repeat")
    speed: float | None = Field(default=None, gt=0.0, description="SPEED 倍率")
    reframe: ReframeHint | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> "EditOp":
        if self.source_end_ms < self.source_start_ms:
            raise ValueError(f"source_end_ms({self.source_end_ms}) < source_start_ms")
        return self


class ContinuityNote(ContractModel):
    """连续性处理说明（docs/modules/42 §4.2）。"""

    kind: ContinuityRuleKind
    at_ms: int = Field(ge=0, description="发生位置（源时间）")
    detail: str = Field(min_length=1)


class ReeditPlan(ContractModel):
    """原片重剪计划（docs/modules/42 §4）：有序操作 + 连续性说明 + 输出总时长。"""

    id: str = Field(min_length=1)
    source_transcript_id: str | None = None
    source_asset_id: str | None = None
    ops: list[EditOp] = Field(default_factory=list)
    continuity: list[ContinuityNote] = Field(default_factory=list)
    kept_duration_ms: int = Field(ge=0, description="保留段总时长（输出时长）")
    created_at: datetime
