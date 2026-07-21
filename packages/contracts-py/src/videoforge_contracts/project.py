from datetime import datetime

from pydantic import Field

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import CreationMode, ExecutionPolicy, ProjectStatus


class Project(ContractModel):
    """一条创作任务的业务根（docs/architecture/31 §1.2）。"""

    id: str = Field(min_length=1, description="UUIDv7/ULID，外部不可枚举")
    title: str = Field(min_length=1, max_length=300)
    vertical: str = Field(min_length=1, description="内容方向，如 ai-tech")
    source_language: str = Field(min_length=2, description="BCP-47，如 zh-CN")
    target_languages: list[str] = Field(min_length=1, description="BCP-47 列表")
    creation_mode: CreationMode
    status: ProjectStatus = ProjectStatus.DRAFT
    execution_policy: ExecutionPolicy = ExecutionPolicy.LOCAL_PREFERRED
    trend_cluster_id: str | None = Field(default=None, description="来源热点聚类")
    source_asset_ids: list[str] = Field(default_factory=list)
    channel_profile_id: str | None = None
    template_version_id: str | None = None
    workflow_id: str | None = Field(default=None, description="Temporal workflow id")
    budget_policy: str | None = Field(
        default=None, description="预算策略引用；超限时进入 WAITING_FOR_BUDGET_APPROVAL"
    )
    created_at: datetime
    updated_at: datetime
