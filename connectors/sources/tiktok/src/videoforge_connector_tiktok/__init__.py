"""TikTok 发现连接器公共 API。解析/错误映射/fetcher 复用 provider-sdk 发现 kit。"""

from videoforge_connector_tiktok.connector import (
    TikTokDiscoveryConnector,
    load_tiktok_descriptor,
)
from videoforge_provider_sdk import (
    CANARY_KEYWORD,
    ConnectorError,
    DiscoveryFetcher,
    FixtureFetcher,
    ParseError,
    UnconfiguredFetcher,
    map_http_status,
    map_payload_error,
    parse_items,
)

TikTokFetcher = DiscoveryFetcher

__all__ = [
    "CANARY_KEYWORD",
    "ConnectorError",
    "FixtureFetcher",
    "ParseError",
    "TikTokDiscoveryConnector",
    "TikTokFetcher",
    "UnconfiguredFetcher",
    "load_tiktok_descriptor",
    "map_http_status",
    "map_payload_error",
    "parse_items",
]
