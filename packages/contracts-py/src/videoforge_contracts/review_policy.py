"""审核策略 + 版本签名 + Trusted Template 状态机合同（docs/modules/44 §1/§2/§12）。

VF-501 目标：**审核策略 + 队列**层——决定一个版本是否需要人工审核（ALWAYS /
NEW_TEMPLATE_ONLY / AUTO），把审核决定绑定到**具体版本内容**（修改即失效，§1.2/§13），
并用状态机管理模板 NEW → TRUSTED 升级（§12）。

**安全说明（重要）**：`ReviewDecision.signature` 是**无密钥的内容绑定摘要**（sha256 覆盖
entity_id + entity_version + content_digest + 决定字段），只提供"审批绑定到被审的确切内容、
一改即失效"的**完整性/失效**保证，**不提供密码学不可否认性**（那需 HMAC/非对称签名 +
密钥管理，属安全硬化项，接入真实签名时走 security 评审）。发布相关的真实平台凭据/密钥
（§8）是 stop-condition，不在本层。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel


class ReviewDecisionKind(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"  # 驳回 + 要求局部重跑/改


class ReviewScope(StrEnum):
    """审批对象的粒度（§1.2）。"""

    VARIANT = "VARIANT"
    PACKAGE = "PACKAGE"
    TEMPLATE = "TEMPLATE"
    PROJECT = "PROJECT"


class ReviewPolicyMode(StrEnum):
    """§12 审核策略：何时需要人工审核。"""

    ALWAYS = "ALWAYS"  # 每个版本都需人工
    NEW_TEMPLATE_ONLY = "NEW_TEMPLATE_ONLY"  # 仅 NEW（未受信）模板需人工；TRUSTED 可自动
    AUTO = "AUTO"  # 自动（仅在有阻塞级 QA 时才回退人工）


class ReviewSeverity(StrEnum):
    """§2 审核/发布严重级别（区别于 VF-309 QA 的 BLOCKER/MAJOR/MINOR/INFO 尺度）。"""

    INFO = "INFO"  # 不阻塞
    WARNING = "WARNING"  # 按模板/账号策略决定
    ERROR = "ERROR"  # 阻止发布，可人工修复后重跑
    FATAL = "FATAL"  # 媒体损坏/时间线非法/目标不确定，**不允许覆盖**


class TemplateTrustLevel(StrEnum):
    NEW = "NEW"
    TRUSTED = "TRUSTED"


class ReviewDecision(ContractModel):
    """一次审核决定（§1.2）。绑定到 entity 的具体 version + content_digest。"""

    id: str = Field(min_length=1)
    decision: ReviewDecisionKind
    scope: ReviewScope
    entity_id: str = Field(min_length=1)
    entity_version: int = Field(ge=1)
    content_digest: str = Field(
        min_length=1, description="被审内容的摘要；内容一改即变 → 旧审批失效",
    )
    reviewer_id: str = Field(min_length=1)
    policy_snapshot_id: str = Field(min_length=1)
    qc_report_ids: list[str] = Field(default_factory=list)
    signature: str = Field(
        min_length=1, description="无密钥内容绑定摘要（见模块 docstring 安全说明）",
    )
    note: str | None = None
    created_at: datetime


class ReviewPolicy(ContractModel):
    """审核策略快照（版本化，供 ReviewDecision.policy_snapshot_id 引用）。"""

    id: str = Field(min_length=1)
    mode: ReviewPolicyMode
    warning_blocks: bool = Field(
        default=False, description="WARNING 是否阻塞（模板/账号策略，§2）",
    )
    version: int = Field(default=1, ge=1)
    created_at: datetime


class TemplateTrustCriteria(ContractModel):
    """§12 NEW → TRUSTED 升级阈值（可配）。"""

    min_approved_renders: int = Field(default=20, ge=1)
    recent_window: int = Field(default=20, ge=1)
    max_recent_fatal: int = Field(default=0, ge=0)
    max_error_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    require_owner_approval: bool = True


class TemplateTrustStats(ContractModel):
    """模板当前观测统计（§12 升级依据；均为已知事实，不猜）。"""

    approved_render_count: int = Field(ge=0)
    recent_fatal_count: int = Field(ge=0)
    recent_error_rate: float = Field(ge=0.0, le=1.0)
    qa_meets_standard: bool
    publish_success_ok: bool
    duplicate_publish_ok: bool
    owner_approved: bool


class TemplateTrustState(ContractModel):
    """模板受信状态机的当前状态（§12）。"""

    template_id: str = Field(min_length=1)
    template_version: int = Field(ge=1)
    level: TemplateTrustLevel
    stats: TemplateTrustStats
    criteria: TemplateTrustCriteria = Field(default_factory=TemplateTrustCriteria)
    updated_at: datetime

    @model_validator(mode="after")
    def _check_recent(self) -> "TemplateTrustState":
        if self.stats.recent_fatal_count > self.criteria.recent_window:
            raise ValueError(
                f"recent_fatal_count({self.stats.recent_fatal_count}) 不能超过 "
                f"recent_window({self.criteria.recent_window})"
            )
        return self
