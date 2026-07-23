"""素材规划与解析合同（docs/modules/42 §6）。

AssetPlanSlot 声明"这段时间需要什么样的素材"（角色/检索词/构图/允许来源/fallback），
ResolvedAsset 记录"实际选中的素材是谁、从哪来、许可为何、按什么检索词、用在哪段"——每一条都
必须携带来源+许可+检索词+使用区间（§6.2），用作创作可溯性与合规审计的证据。AssetPlan 是聚合。

真实素材来源（自有库语义检索 / 商业 stock / AI 生成 / 数字人）属停止条件延后；
本合同族提供槽位与结果的类型骨架，纯域负责匹配评分与五级优先级解析。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import AssetLicenseType, AssetRole, AssetSource


class CompositionSpec(ContractModel):
    """构图约束（docs/modules/42 §6.1）：目标画幅 + 安全区。"""

    aspect_ratio: str = Field(min_length=1, description="如 9:16 / 1:1 / 16:9")
    safe_area: str = Field(min_length=1, description="如 center / bottom_third")


class AssetLicense(ContractModel):
    """素材许可（合规审计核心；每个 ResolvedAsset 必带）。"""

    type: AssetLicenseType
    holder: str = Field(min_length=1, description="授权/持有方")
    valid_until: datetime | None = Field(default=None, description="到期时间，缺省=不限")
    notes: str | None = None


class AssetPlanSlot(ContractModel):
    """时间线上的一段素材需求（docs/modules/42 §6.1）。"""

    slot_id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    role: AssetRole
    query: str = Field(min_length=1, description="语义检索词")
    semantic_requirements: list[str] = Field(default_factory=list)
    composition: CompositionSpec
    allowed_sources: list[AssetSource] = Field(
        min_length=1, description="允许的来源；未列出者不得选中（合规约束）"
    )
    fallback: AssetRole | None = Field(default=None, description="全部来源命中失败时的兜底角色")

    @model_validator(mode="after")
    def _end_after_start(self) -> "AssetPlanSlot":
        if self.end_ms < self.start_ms:
            raise ValueError(f"end_ms({self.end_ms}) < start_ms({self.start_ms})")
        return self


class ResolvedAsset(ContractModel):
    """一次解析结果：谁、从哪、什么许可、按什么检索词、用在哪段（§6.2 可溯性四要素）。"""

    slot_id: str = Field(min_length=1, description="所属 AssetPlanSlot")
    asset_id: str = Field(min_length=1)
    source: AssetSource
    license: AssetLicense
    query: str = Field(min_length=1, description="定位到该素材使用的检索词")
    usage_start_ms: int = Field(ge=0, description="素材在输出时间线上的使用起点")
    usage_end_ms: int = Field(ge=0, description="素材在输出时间线上的使用终点")
    match_score: float = Field(ge=0.0, le=1.0)
    reuse_count: int = Field(default=1, ge=1, description="累计被使用次数（供复用惩罚追踪）")
    provider: str | None = Field(default=None, description="来源提供方标识")
    is_fallback: bool = Field(default=False, description="是否 fallback 兜底（非命中）")

    @model_validator(mode="after")
    def _end_after_start(self) -> "ResolvedAsset":
        if self.usage_end_ms < self.usage_start_ms:
            raise ValueError(f"usage_end_ms({self.usage_end_ms}) < usage_start_ms")
        return self


class AssetPlan(ContractModel):
    """聚合：所有槽位 + 解析结果映射。"""

    id: str = Field(min_length=1)
    source_transcript_id: str | None = None
    slots: list[AssetPlanSlot] = Field(default_factory=list)
    resolved: list[ResolvedAsset] = Field(
        default_factory=list, description="按 slot_id 一对一，缺失=未解析（人工兜底）"
    )
    weights_version: str | None = None
    created_at: datetime
