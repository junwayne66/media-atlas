"""TikTok 发现连接器：薄接入 provider-sdk 的 NeutralDiscoveryConnector。

与 douyin 同构，仅平台配置不同。编排/解析/错误映射/熔断/canary 全部复用 kit。
真实抓取未实现（停止条件）。
"""

from pathlib import Path

from videoforge_contracts import ProviderDescriptor
from videoforge_provider_sdk import (
    CircuitBreaker,
    DiscoveryFetcher,
    DiscoveryMode,
    NeutralDiscoveryConnector,
    load_descriptor,
)

CONNECTOR_NAME = "source.tiktok"
COLLECTOR_VERSION = "tiktok-collector@0.1.0"

_SOURCE_CONFIDENCE = {
    DiscoveryMode.MANUAL: 0.75,
    DiscoveryMode.KEYWORD: 0.6,
    DiscoveryMode.ACCOUNT: 0.6,
    DiscoveryMode.BOARD: 0.6,
}


def load_tiktok_descriptor() -> ProviderDescriptor:
    return load_descriptor(Path(__file__).resolve().parents[2] / "descriptor.yaml")


class TikTokDiscoveryConnector(NeutralDiscoveryConnector):
    def __init__(
        self,
        descriptor: ProviderDescriptor | None = None,
        *,
        fetcher: DiscoveryFetcher | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        super().__init__(
            descriptor=descriptor or load_tiktok_descriptor(),
            connector_name=CONNECTOR_NAME,
            platform="tiktok",
            collector_version=COLLECTOR_VERSION,
            source_confidence=_SOURCE_CONFIDENCE,
            fetcher=fetcher,
            breaker=breaker,
        )
