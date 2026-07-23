"""创意规划合同（docs/modules/42 §1/§2/§3.2）。

CreativeOpportunity（热点 + 源蓝图触发的机会）→ CreativeBrief（目标/角度/受众/平台/时长预算/
禁用/视觉配比/CTA）+ ClaimTable（事实/证据/时效/置信度/允许表述）。结构重写只消费 Brief 的
抽象节拍 + ClaimTable 的经核验事实——模型生成的新增事实进 UNVERIFIED，发布前不能自动通过。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.blueprint import EvidenceSpan
from videoforge_contracts.enums import ClaimSourceStatus, CreationMode


class CreativeOpportunity(ContractModel):
    """一次二创机会：热点聚类 + 源蓝图 + 为何值得做（M04 输入）。"""

    id: str = Field(min_length=1)
    trend_cluster_id: str | None = None
    blueprint_id: str | None = Field(default=None, description="参考视频的 VideoBlueprint")
    source_asset_ids: list[str] = Field(default_factory=list)
    vertical: str | None = None
    rationale: str = Field(min_length=1, description="为何是机会（热点证据/角度空白等）")
    target_platform: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    created_at: datetime


class VisualMix(ContractModel):
    """视觉配比（docs/modules/42 §2）。四类占比之和应 ≈ 1。"""

    talking_head: float = Field(default=0.0, ge=0.0, le=1.0)
    screen_demo: float = Field(default=0.0, ge=0.0, le=1.0)
    broll: float = Field(default=0.0, ge=0.0, le=1.0)
    info_card: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> "VisualMix":
        total = self.talking_head + self.screen_demo + self.broll + self.info_card
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"visual_mix 四类占比之和应 ≈ 1，得 {total:.3f}")
        return self


class BriefHook(ContractModel):
    """开场钩子。"""

    type: str = Field(min_length=1, description="如 counter_intuitive_claim")
    promise: str = Field(min_length=1, description="给观众的承诺")


class CreativeBrief(ContractModel):
    """创意简报（docs/modules/42 §2）。必须引用热点证据/Claims。"""

    id: str = Field(min_length=1)
    opportunity_id: str | None = None
    blueprint_id: str | None = None
    claim_table_id: str | None = None
    objective: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    duration_target_ms: int = Field(gt=0)
    creation_mode: CreationMode
    angle: str = Field(min_length=1)
    hook: BriefHook | None = None
    must_cover_claim_ids: list[str] = Field(default_factory=list, description="必须覆盖的 Claim")
    avoid: list[str] = Field(default_factory=list, description="禁用：照抄标题/未证实结论等")
    visual_mix: VisualMix | None = None
    cta: str | None = None
    created_at: datetime


class ClaimTableEntry(ContractModel):
    """ClaimTable 条目（docs/modules/42 §3.2）：事实 + 证据 + 时效 + 置信 + 允许表述。"""

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    fact_status: ClaimSourceStatus = ClaimSourceStatus.UNVERIFIED
    evidence: list[EvidenceSpan] = Field(min_length=1, description="至少一条证据，禁凭空事实")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    recency: str | None = Field(default=None, description="时效标记，如 as_of_2026-07")
    allowed_phrasings: list[str] = Field(default_factory=list, description="允许的表述方式")
    usable_in_rewrite: bool = Field(
        default=True, description="是否可直接用于改写（DISPUTED 须人工核实）"
    )


class ClaimTable(ContractModel):
    """经核验事实表，供结构重写消费。"""

    id: str = Field(min_length=1)
    source_blueprint_id: str | None = None
    entries: list[ClaimTableEntry] = Field(default_factory=list)
    created_at: datetime
