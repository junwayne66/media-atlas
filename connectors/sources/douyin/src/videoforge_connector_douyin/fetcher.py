"""抓取端口：连接器不直接做网络 I/O，把「取原始响应」隔离到 fetcher。

- UnconfiguredFetcher：默认。官方需凭据/App 审核、L4 实时抓取需授权——均未配置，
  返回 APP_REVIEW_REQUIRED（停止条件），绝不静默返回空榜单。
- FixtureFetcher：测试用，回放录制/合成响应，全链路不触网。
真实实时 fetcher 有意不实现（docs/implementation/53 §10 停止条件）。
"""

from typing import Any, Protocol

from videoforge_connector_douyin.error_mapping import ConnectorError
from videoforge_provider_sdk import ConnectorErrorCode, DiscoveryRequest


class DouyinFetcher(Protocol):
    def fetch(self, request: DiscoveryRequest) -> dict[str, Any]: ...


class UnconfiguredFetcher:
    """未配置任何实时路径——返回停止条件，而不是假装无数据。"""

    def fetch(self, request: DiscoveryRequest) -> dict[str, Any]:
        raise ConnectorError(
            ConnectorErrorCode.APP_REVIEW_REQUIRED,
            "抖音实时发现未配置：需官方开放平台凭据+App 审核，或显式授权 L4 公开信号适配器；"
            "在此之前请用手工导入",
        )


class FixtureFetcher:
    """回放预置响应（测试/离线）。按 mode 或 query 选择，缺省用 default。"""

    def __init__(
        self,
        by_mode: dict[str, dict[str, Any]] | None = None,
        *,
        default: dict[str, Any] | None = None,
    ) -> None:
        self._by_mode = by_mode or {}
        self._default = default

    def fetch(self, request: DiscoveryRequest) -> dict[str, Any]:
        payload = self._by_mode.get(str(request.mode), self._default)
        if payload is None:
            raise ConnectorError(ConnectorErrorCode.RESULT_UNKNOWN, "无匹配 fixture")
        return payload
