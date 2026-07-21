from datetime import datetime

from pydantic import Field

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import HealthState, IsolationLevel, ProviderType


class CostModel(ContractModel):
    unit: str = Field(min_length=1, description="计费单位，如 second / 1k_tokens / request")
    estimated_cost_per_unit: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class ProviderHealth(ContractModel):
    status: HealthState = HealthState.UNKNOWN
    last_success_at: datetime | None = None
    last_error: str | None = None


class ProviderDescriptor(ContractModel):
    """Provider 注册描述（docs/10-module-overview.md §4 必声明字段）。"""

    name: str = Field(min_length=1, description="唯一名，如 asr.whisper-cpp")
    provider_type: ProviderType
    version: str = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)
    execution_location: str = Field(pattern=r"^(local|cloud|hybrid)$", description="默认执行位置")
    languages: list[str] = Field(default_factory=list, description="支持语言，BCP-47")
    platforms: list[str] = Field(default_factory=list, description="适用平台，如 douyin/tiktok")
    cost_model: CostModel | None = None
    license_notes: str | None = Field(
        default=None, description="代码/模型/权重许可证要点；来源 third_party_manifest.yaml"
    )
    isolation_level: IsolationLevel = IsolationLevel.L0
    health: ProviderHealth = Field(default_factory=ProviderHealth)
    required_secrets: list[str] = Field(
        default_factory=list, description="所需 Secret 的名称（非值）"
    )
