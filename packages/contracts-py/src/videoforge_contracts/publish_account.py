"""平台账号合同（docs/modules/44 §8 账号与 Secret）。

VF-506 起步：`PlatformAccount` **不含任何明文 Secret**——只存 `credential_ref`（指向加密
Secret 存储的**不透明 Handle**）+ 健康状态（§8）。OAuth Refresh Token 服务端加密、浏览器
Cookie/Android 会话留在 Desktop/Device，控制中心只保存 Handle。

**红线**：本合同结构上**没有** token/password/cookie 字段——只有 handle 引用；任何发布操作
写 AuditEvent（审计在应用层）。真实设备/平台凭据本身是 stop-condition，不在本层。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.publish_preflight import (
    AccountStatus,
    PublishMethod,
    PublishPlatform,
)


class AccountBinding(StrEnum):
    """会话/凭据留存位置（§8）。"""

    SERVER_ENCRYPTED = "SERVER_ENCRYPTED"  # OAuth Refresh Token 服务端加密
    DESKTOP = "DESKTOP"  # 浏览器 Cookie 留在 Desktop
    DEVICE = "DEVICE"  # Android 账号会话留在真机


class PlatformAccount(ContractModel):
    """一个平台账号（§8）——**只存 handle，不存 secret**。"""

    id: str = Field(min_length=1)
    platform: PublishPlatform
    display_name: str = Field(min_length=1)
    external_account_id: str = Field(min_length=1)
    credential_ref: str = Field(
        min_length=1,
        description="加密 Secret 存储的不透明 Handle——**绝不是** token/password 本体",
    )
    binding: AccountBinding = AccountBinding.SERVER_ENCRYPTED
    connector_preferences: list[PublishMethod] = Field(default_factory=list)
    review_policy_id: str | None = None
    publishing_window: str | None = None
    locale: str = Field(min_length=1)
    status: AccountStatus = AccountStatus.UNKNOWN
    last_verified_at: datetime | None = None
    device_binding_id: str | None = None

    @model_validator(mode="after")
    def _no_secret_leak(self) -> "PlatformAccount":
        # 结构上无 secret 字段；再挡一道防误填 token 本体：只要 credential_ref **任意位置**
        # 出现明文凭据特征串就拒（子串扫描，含 'ch-eyJ...' 这类前缀包裹的 JWT——verifier 揭示
        # 前缀检查的漏网）。这是"防误粘贴"纵深防御，非结构保证。
        low = self.credential_ref.lower()
        for bad in ("bearer ", "eyj", "password=", "secret=", "-----begin", "refresh_token"):
            if bad in low:
                raise ValueError(
                    "credential_ref 含明文凭据特征串；必须是加密存储的不透明 Handle（§8）"
                )
        return self
