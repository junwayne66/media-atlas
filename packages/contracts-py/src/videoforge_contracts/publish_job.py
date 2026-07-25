"""发布任务 + 幂等状态机合同（docs/modules/44 §4 PublishWorkflow + §5 幂等与未知状态）。

VF-503 目标（**Fake-first，不触真实平台**）：把发布抽象成一个**幂等的 PublishJob 状态机**——
本地先建唯一 Job（`idempotency_key` = §5 公式），走 上传→提交→校验→保存外部 ID 的生命周期；
**同一 Job 反复重试绝不重复发布**（§5/§13）：网络超时后先查状态/账号最近帖子，匹配到已存在的
外部帖子就标 `SUCCEEDED_RECONCILED`，绝不盲目重发。挑战/授权失败 → `WAITING_FOR_HUMAN`。

**红线**：真实 TikTok 发布（Content Posting API Direct Post、Creator Info、上传/Webhook）需
**真实平台账号 + 官方 API + 应用审核 + 凭据 → stop-condition**。本层只落地契约 + 状态机 +
Fake/Unconfigured executor，**无 live network**（grep-clean），真实发布路径返回 UNCONFIGURED。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.publish_preflight import PublishMethod, PublishPlatform


class PublishState(StrEnum):
    """§4 发布状态机的状态。"""

    PENDING = "PENDING"  # 已建 Job，未开始
    PREFLIGHT_BLOCKED = "PREFLIGHT_BLOCKED"  # 预检未过（VF-502 阻塞）
    AWAITING_AUTH = "AWAITING_AUTH"  # 需授权/刷新 Token
    UPLOADING = "UPLOADING"  # 上传媒体中
    SUBMITTED = "SUBMITTED"  # 已提交发帖，待确认（此后绝不重发）
    VERIFYING = "VERIFYING"  # 查状态/对账中
    SUCCEEDED = "SUCCEEDED"  # 确认发布成功，已存外部 ID
    SUCCEEDED_RECONCILED = "SUCCEEDED_RECONCILED"  # §5：对账发现已存在的外部帖子
    FAILED = "FAILED"  # 终态失败
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"  # 挑战/授权失败 → 人工（§4.5/§13）


class PublishAttempt(ContractModel):
    """一次平台调用尝试（§5：每次保存请求摘要 + 外部 upload/post token）。"""

    attempt: int = Field(ge=1)
    request_digest: str = Field(min_length=1)
    external_upload_token: str | None = None
    external_post_token: str | None = Field(
        default=None,
        description="已提交发帖的外部令牌；有值即视为已提交，用于幂等对账",
    )
    detail: str | None = None
    at: datetime


class PublishJob(ContractModel):
    """一个幂等发布任务（§4/§5）。同 idempotency_key 只应存在一个 Job。"""

    id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    platform: PublishPlatform
    method: PublishMethod
    render_digest: str = Field(min_length=1)
    metadata_digest: str = Field(min_length=1)
    scheduled_window: str = Field(
        min_length=1,
        description="计划窗口标识（如 ISO 时间或 'immediate'）",
    )
    state: PublishState
    external_post_id: str | None = None
    external_url: str | None = None
    content_fingerprint: str | None = None
    attempts: list[PublishAttempt] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _check_success(self) -> "PublishJob":
        if self.state in (PublishState.SUCCEEDED, PublishState.SUCCEEDED_RECONCILED):
            if not self.external_post_id:
                raise ValueError(
                    f"{self.state.value} 必须携带 external_post_id（成功即已保存外部帖子 ID）"
                )
        return self
