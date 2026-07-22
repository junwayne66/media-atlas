"""TikTok 连接器端到端（复用发现 kit）：四态可诊断、验证码转人工、手工导入回退、
canary、descriptor L4。全链路不触网。"""

from tk_fixtures import load_tiktok_fixture

from videoforge_connector_tiktok import (
    FixtureFetcher,
    TikTokDiscoveryConnector,
    UnconfiguredFetcher,
)
from videoforge_provider_sdk import (
    ConnectorErrorCode,
    DiscoveryMode,
    DiscoveryRequest,
    DiscoveryStatus,
)


def test_descriptor_loads_as_l4_multilingual() -> None:
    c = TikTokDiscoveryConnector()
    assert c.descriptor.name == "source.tiktok"
    assert c.descriptor.isolation_level == "L4"
    assert set(c.descriptor.languages) == {"en-US", "zh-CN"}
    assert c.descriptor.platforms == ["tiktok"]


def test_manual_import_always_available() -> None:
    c = TikTokDiscoveryConnector()  # 默认未配置
    result = c.import_manual(load_tiktok_fixture("manual_import.json"))
    assert result.status == DiscoveryStatus.OK
    assert result.connector == "source.tiktok"
    snap = result.snapshots[0]
    assert snap.item_id == "tt-manual-1"
    assert snap.platform == "tiktok"
    assert snap.source_confidence == 0.75


def test_discover_board_ok_with_null_metrics_preserved() -> None:
    c = TikTokDiscoveryConnector(
        fetcher=FixtureFetcher(default=load_tiktok_fixture("board_response.json"))
    )
    result = c.discover(DiscoveryRequest(DiscoveryMode.BOARD, "us-hot", locale="en-US"))
    assert result.status == DiscoveryStatus.OK
    assert len(result.snapshots) == 2
    assert result.snapshots[1].comments is None  # null 保留
    assert result.snapshots[0].views == 2400000


def test_empty_is_diagnosable_not_failure() -> None:
    c = TikTokDiscoveryConnector(
        fetcher=FixtureFetcher(default=load_tiktok_fixture("empty_response.json"))
    )
    result = c.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "obscure"))
    assert result.status == DiscoveryStatus.EMPTY
    assert result.error_code is None


def test_unconfigured_is_stop_condition() -> None:
    c = TikTokDiscoveryConnector(fetcher=UnconfiguredFetcher())
    result = c.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "ai"))
    assert result.status == DiscoveryStatus.UNCONFIGURED
    assert result.error_code == ConnectorErrorCode.APP_REVIEW_REQUIRED


def test_challenge_routes_to_human() -> None:
    c = TikTokDiscoveryConnector(
        fetcher=FixtureFetcher(default=load_tiktok_fixture("challenge_response.json"))
    )
    result = c.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "ai"))
    assert result.status == DiscoveryStatus.CHALLENGE
    assert result.error_code == ConnectorErrorCode.CHALLENGE_REQUIRED


def test_canary_unconfigured_by_default() -> None:
    assert TikTokDiscoveryConnector().health_check().status == DiscoveryStatus.UNCONFIGURED
