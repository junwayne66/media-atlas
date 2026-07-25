"""排序器校准合同（docs/modules/44 §11 末：样本足够后校准热点/Highlight，先离线评估再少量探索）。

VF-604 目标（P6 收官）：用 VF-601..603 的账号内相对指标 + 学习信号，对**热点/Highlight 排序器的
权重**做**可解释、有界的校准**——**先离线评估，再少量探索并保留探索流量**（§11）。

**红线**：
- **无全量自动上线**：`CalibrationDecision` 没有"全量替换"值——最强动作只是 `EXPLORE`（候选获得
  受限比例的探索流量），结构上禁止一步切换到黑盒排序器。
- **离线评估门**：候选只有在**离线**排序指标（Spearman 秩相关 / Top-k 命中）以足够样本超过当前
  一个 margin 时才 `promotable`。
- **保留探索流量**：`exploration_fraction ≤ max_exploration_fraction`（默认 0.2）。
- **有界可解释权重**：系数 ≥0（承接 VF-101 幅度系数），候选是有界微调、模板版本化、可审计。
- **样本不足不校准**：不足 → `INSUFFICIENT_SAMPLES`，绝不提升。
- **null≠0**（承接 VF-601）：相对结局为 None 的样本不计入离线评估。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel

# 保留探索流量上限（§11："少量探索"）。
MAX_EXPLORATION_FRACTION = 0.2


class RankerKind(StrEnum):
    TREND_HOT = "TREND_HOT"  # VF-101 hot_score 权重
    HIGHLIGHT = "HIGHLIGHT"  # VF-303 highlight_score 权重


class CalibrationDecision(StrEnum):
    """校准决策。**故意没有"全量替换"值**——最强动作只是 EXPLORE（§11：先离线再少量探索）。"""

    KEEP_CURRENT = "KEEP_CURRENT"
    EXPLORE = "EXPLORE"  # 候选获得 exploration_fraction 的探索流量
    INSUFFICIENT_SAMPLES = "INSUFFICIENT_SAMPLES"


class RankerWeights(ContractModel):
    """排序器权重（通用线性表示；系数为 ≥0 幅度——正负号在打分公式里，承接 VF-101）。"""

    ranker_kind: RankerKind
    template_version: str = Field(min_length=1)
    coefficients: dict[str, float] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_non_negative(self) -> "RankerWeights":
        for name, value in self.coefficients.items():
            if value < 0:
                raise ValueError(f"系数 {name}={value} 不能为负（幅度系数 ≥0）")
        return self


class RankingSample(ContractModel):
    """一条历史排序样本（离线评估输入；非顶层注册）。relative_outcome=None 表示结局未知（排除）。"""

    item_id: str = Field(min_length=1)
    features: dict[str, float] = Field(default_factory=dict)
    relative_outcome: float | None = None


class RankingEvalResult(ContractModel):
    """一组权重在历史样本上的**离线**排序质量。样本不足或无方差时指标为 null。"""

    ranker_kind: RankerKind
    template_version: str = Field(min_length=1)
    rank_correlation: float | None = Field(default=None, ge=-1, le=1)
    top_k: int = Field(ge=1)
    top_k_hit_rate: float | None = Field(default=None, ge=0, le=1)
    sample_count: int = Field(ge=0)
    enough_samples: bool


class CalibrationProposal(ContractModel):
    """一次校准提案：当前 vs 候选权重 + 双方离线评估 + 决策。

    交叉校验把 §11 红线变成合同硬拦：EXPLORE 必须 promotable 且 0<fraction≤max；非 EXPLORE 时
    fraction 必须为 0；不可 promotable 却 EXPLORE；探索比例不得超上限。
    """

    ranker_kind: RankerKind
    current: RankerWeights
    candidate: RankerWeights
    current_eval: RankingEvalResult
    candidate_eval: RankingEvalResult
    improvement: float
    promotable: bool
    decision: CalibrationDecision
    exploration_fraction: float = Field(ge=0, le=MAX_EXPLORATION_FRACTION)
    # 每提案的探索上限只能收紧、绝不能放宽——字段本身封顶在硬常量 MAX_EXPLORATION_FRACTION，
    # 使 max=1.0 这类"全量上线"提案在构造/反序列化时就被拒（verifier REFUTED 的漏洞修复）。
    max_exploration_fraction: float = Field(
        default=MAX_EXPLORATION_FRACTION, gt=0, le=MAX_EXPLORATION_FRACTION
    )
    generated_at: datetime
    note: str = ""

    @model_validator(mode="after")
    def _check_decision_and_exploration(self) -> "CalibrationProposal":
        # 绝对硬上限（独立于 self.max_exploration_fraction，防篡改）：绝不全量上线。
        if self.exploration_fraction > MAX_EXPLORATION_FRACTION:
            raise ValueError(
                f"exploration_fraction={self.exploration_fraction} 超过硬上限 "
                f"{MAX_EXPLORATION_FRACTION}（§11：只能少量探索，绝不全量自动上线）"
            )
        if self.exploration_fraction > self.max_exploration_fraction:
            raise ValueError(
                f"exploration_fraction={self.exploration_fraction} "
                f"超过上限 {self.max_exploration_fraction}（须保留探索流量）"
            )
        if self.decision is CalibrationDecision.EXPLORE:
            if not self.promotable:
                raise ValueError("EXPLORE 必须 promotable=True（先离线评估通过）")
            if self.exploration_fraction <= 0:
                raise ValueError("EXPLORE 的 exploration_fraction 必须 > 0")
        else:
            if self.exploration_fraction != 0:
                raise ValueError("非 EXPLORE 决策的 exploration_fraction 必须为 0")
        # ranker_kind 一致
        kinds = {
            self.ranker_kind, self.current.ranker_kind, self.candidate.ranker_kind,
            self.current_eval.ranker_kind, self.candidate_eval.ranker_kind,
        }
        if len(kinds) != 1:
            raise ValueError("current/candidate/eval 的 ranker_kind 必须一致")
        return self
