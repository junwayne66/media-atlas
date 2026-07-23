"""热门片段识别合同（docs/modules/42 §5）。

候选窗口在句子/语义 Beat 边界上生成 → 11 项特征子分（模型判断）→ 加权 highlight_score（域内确定性
聚合，系数读 HighlightWeights 模板）→ 重叠去重 + MMR 多样性 → Top-N HighlightCandidate（带 reason
codes + 人工标签）。predicted_retention 是后续校准项，无训练数据时保持 null，绝不伪装成准确预测。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import HighlightLabel, HighlightReason


class HighlightFeatures(ContractModel):
    """单个候选窗口的 11 项特征子分（docs/modules/42 §5.2），各 ∈ [0,1]。由模型判断产出。"""

    hook_strength: float = Field(ge=0.0, le=1.0)
    self_containedness: float = Field(ge=0.0, le=1.0)
    information_density: float = Field(ge=0.0, le=1.0)
    surprise_or_conflict: float = Field(ge=0.0, le=1.0)
    emotional_energy: float = Field(ge=0.0, le=1.0)
    topic_relevance: float = Field(ge=0.0, le=1.0)
    visual_activity: float = Field(ge=0.0, le=1.0)
    speaker_prominence: float = Field(ge=0.0, le=1.0)
    ending_payoff: float = Field(ge=0.0, le=1.0)
    context_dependency: float = Field(ge=0.0, le=1.0, description="惩罚项：越高越依赖上下文")
    technical_defect: float = Field(ge=0.0, le=1.0, description="惩罚项：越高技术瑕疵越重")


class HighlightWeights(ContractModel):
    """highlight_score 权重模板（docs/modules/42 §5.2）。系数为量级（≥0）；惩罚项的负号在公式里。

    默认值与文档 §5.2 一一对应。模板可版本化，highlight_score 读系数后 bit 级可复现。
    """

    template_version: str = Field(min_length=1)
    hook_strength: float = Field(default=0.20, ge=0.0)
    self_containedness: float = Field(default=0.16, ge=0.0)
    information_density: float = Field(default=0.14, ge=0.0)
    surprise_or_conflict: float = Field(default=0.12, ge=0.0)
    emotional_energy: float = Field(default=0.10, ge=0.0)
    topic_relevance: float = Field(default=0.09, ge=0.0)
    visual_activity: float = Field(default=0.07, ge=0.0)
    speaker_prominence: float = Field(default=0.06, ge=0.0)
    ending_payoff: float = Field(default=0.06, ge=0.0)
    context_dependency: float = Field(default=0.12, ge=0.0, description="公式里取负")
    technical_defect: float = Field(default=0.08, ge=0.0, description="公式里取负")


class HighlightCandidate(ContractModel):
    """一个热门片段候选（docs/modules/42 §5）。时间窗落在句子边界，附特征/评分/理由/人工标签。"""

    id: str = Field(min_length=1)
    source_transcript_id: str | None = None
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    segment_ids: list[str] = Field(default_factory=list, description="构成窗口的转录段，句子边界")
    score: float = Field(description="加权 highlight_score，可为负（惩罚项占优时）")
    features: HighlightFeatures
    reason_codes: list[HighlightReason] = Field(default_factory=list)
    human_label: HighlightLabel = HighlightLabel.UNREVIEWED
    human_label_reason: str | None = Field(default=None, description="人工选中/放弃原因 → 训练标签")
    predicted_retention: float | None = Field(
        default=None, ge=0.0, le=1.0, description="校准项，无训练数据时为 null，不伪装预测"
    )
    weights_version: str | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> "HighlightCandidate":
        if self.end_ms < self.start_ms:
            raise ValueError(f"end_ms({self.end_ms}) < start_ms({self.start_ms})")
        return self


class HighlightSet(ContractModel):
    """一次热门片段识别的 Top-N 结果集（docs/modules/42 §5.3）。"""

    id: str = Field(min_length=1)
    source_transcript_id: str | None = None
    candidates: list[HighlightCandidate] = Field(default_factory=list)
    weights_version: str | None = None
    feature_provider: str | None = None
    created_at: datetime
