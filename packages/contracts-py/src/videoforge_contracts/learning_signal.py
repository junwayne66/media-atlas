"""学习信号合同（docs/modules/44 §11 归因与学习信号）。

VF-603 目标：把**过程信号**（人工选择/驳回、QA 警告、人工修改次数、发布时热度、发布延迟、时长…）
与**账号内相对表现**（承接 VF-602）做**可解释统计关联**——**只做相关，不训练黑盒"爆款模型"**（§11）。

**红线**：
- **关联非因果**（`association_only` 恒 True）——学习信号只报"高信号组表现相对更高/更低的**相关**"，
  绝不表述成"做 X 就能爆"的因果建议。
- **可解释**：关联度是透明的 Spearman 秩相关（∈[-1,1]）+ 分桶中位数——可复现、无黑盒。
- **账号内相对**（承接 VF-602）：结局用账号内相对指标，绝不跨账号比绝对播放。
- **样本不足不下结论**：`enough_samples`/`INSUFFICIENT`——样本不足只报低置信，不给方向。
- **null 语义**（承接 VF-601）：信号或结局缺失的样本对不计入，绝不当 0。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.performance import MetricField
from videoforge_contracts.publish_preflight import PublishPlatform


class SignalKind(StrEnum):
    """§11 可分析的过程信号。"""

    QA_WARNING_COUNT = "QA_WARNING_COUNT"
    MANUAL_EDIT_COUNT = "MANUAL_EDIT_COUNT"
    HUMAN_SELECTED = "HUMAN_SELECTED"
    REJECTED_THEN_REVISED = "REJECTED_THEN_REVISED"
    TREND_HOTNESS = "TREND_HOTNESS"
    PUBLISH_DELAY = "PUBLISH_DELAY"
    DURATION = "DURATION"
    HAS_MUSIC = "HAS_MUSIC"


class SignalDirection(StrEnum):
    """信号与相对表现的关联方向（**相关**，非因果）。"""

    POSITIVE = "POSITIVE"  # 信号越高，相对表现越高（相关）
    NEGATIVE = "NEGATIVE"  # 信号越高，相对表现越低（相关）
    NONE = "NONE"  # 无明显关联
    INSUFFICIENT = "INSUFFICIENT"  # 样本不足，不下结论


class SignalBucketStat(ContractModel):
    """按信号值分桶后，该桶内的相对表现统计。"""

    label: str = Field(min_length=1)
    sample_count: int = Field(ge=0)
    median_relative: float | None = None
    enough_samples: bool


class LearningSignalResult(ContractModel):
    """一个信号对某 (age, metric) 相对结局的关联分析结果。

    `correlation` 是 Spearman 秩相关 ∈[-1,1]（透明可复现）；`direction` 由相关度 + 阈值 +
    样本量得出；`association_only` 恒 True——**关联非因果**（§11 红线）。
    """

    signal: SignalKind
    metric: MetricField
    age_hours: float = Field(ge=0)
    correlation: float | None = Field(default=None, ge=-1, le=1)
    direction: SignalDirection
    sample_count: int = Field(ge=0)
    enough_samples: bool
    buckets: list[SignalBucketStat] = Field(default_factory=list)
    association_only: bool = True
    note: str = ""

    @model_validator(mode="after")
    def _check_association_and_direction(self) -> "LearningSignalResult":
        if self.association_only is not True:
            raise ValueError("association_only 必须为 True（§11：关联非因果，绝不作因果建议）")
        # 样本不足绝不给出方向性结论。
        if not self.enough_samples and self.direction not in (
            SignalDirection.INSUFFICIENT,
            SignalDirection.NONE,
        ):
            raise ValueError("样本不足时 direction 只能是 INSUFFICIENT/NONE")
        return self


class LearningReport(ContractModel):
    """某账号在某 (age, metric) 视角下，各过程信号与相对表现的关联报告。"""

    account_id: str = Field(min_length=1)
    platform: PublishPlatform
    generated_at: datetime
    age_hours: float = Field(ge=0)
    metric: MetricField
    min_samples: int = Field(ge=1)
    signals: list[LearningSignalResult] = Field(default_factory=list)
