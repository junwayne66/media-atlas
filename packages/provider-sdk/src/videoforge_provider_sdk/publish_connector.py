"""发布连接器端口 —— **上报能力/授权/审核/账号状态**（docs/modules/44 §3）。

§3 红线：**Connector 返回能力，不由 UI 猜测**。本端口只让连接器**上报**它能做什么
（方法/直发/授权/客户端审核/账号状态/容器/文件上限），domain `run_preflight` 据此预检。

**真实发布（上传 / Direct Post / Creator Info 查询 / 状态 Webhook）是 VF-503 起的
stop-condition**——需真实平台账号 + 官方 API + 应用审核。本端口**不触真实平台**：
`UnconfiguredPublishConnector` 诚实上报"未授权/不可用"；`FakePublishConnector` 回放
构造注入的能力，零网络。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from videoforge_contracts import (
    AccountStatus,
    AuthStatus,
    ClientReviewStatus,
    PublishConnectorCapability,
    PublishMethod,
    PublishPlatform,
)


@runtime_checkable
class PublishConnector(Protocol):
    """§3 发布连接器：只上报能力，不由 UI 猜。真实发布延后（VF-503 stop-condition）。"""

    platform: PublishPlatform
    method: PublishMethod

    def capabilities(self) -> PublishConnectorCapability: ...


class UnconfiguredPublishConnector:
    """诚实占位：无真实平台账号/凭据 → 上报不可用 + 未授权（绝不假装能发）。"""

    def __init__(
        self, *, platform: PublishPlatform, method: PublishMethod = PublishMethod.OFFICIAL_API
    ) -> None:
        self.platform = platform
        self.method = method

    def capabilities(self) -> PublishConnectorCapability:
        return PublishConnectorCapability(
            platform=self.platform,
            method=self.method,
            available=False,
            direct_post=False,
            auth_status=AuthStatus.UNAUTHORIZED,
            client_review_status=ClientReviewStatus.UNAUDITED,
            account_status=AccountStatus.UNKNOWN,
            notes="未配置真实平台账号/凭据（真实发布属 VF-503 stop-condition）",
        )


class FakePublishConnector:
    """确定性 Fake：回放构造注入的能力（零网络、不触真实平台）。

    用于预检/方法选择的 pipeline 开发：可注入不同授权/审核/账号状态驱动 domain 分支。
    """

    def __init__(
        self,
        *,
        platform: PublishPlatform,
        method: PublishMethod = PublishMethod.OFFICIAL_API,
        available: bool = True,
        direct_post: bool = True,
        auth_status: AuthStatus = AuthStatus.AUTHORIZED,
        client_review_status: ClientReviewStatus = ClientReviewStatus.APPROVED,
        account_status: AccountStatus = AccountStatus.ACTIVE,
        supported_containers: tuple[str, ...] = ("mp4", "mov"),
        max_file_size_bytes: int | None = None,
    ) -> None:
        self.platform = platform
        self.method = method
        self._cap = PublishConnectorCapability(
            platform=platform,
            method=method,
            available=available,
            direct_post=direct_post,
            auth_status=auth_status,
            client_review_status=client_review_status,
            account_status=account_status,
            supported_containers=list(supported_containers),
            max_file_size_bytes=max_file_size_bytes,
            notes="Fake：非真实平台连接器，仅上报注入能力",
        )

    def capabilities(self) -> PublishConnectorCapability:
        return self._cap


__all__ = [
    "FakePublishConnector",
    "PublishConnector",
    "UnconfiguredPublishConnector",
]
