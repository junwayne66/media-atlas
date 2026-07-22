"""可复用发现 kit 的直接覆盖（不经具体连接器）。各平台连接器的测试另做端到端。"""

import pytest

from videoforge_contracts import ProviderDescriptor
from videoforge_provider_sdk import (
    CircuitBreaker,
    ConnectorError,
    ConnectorErrorCode,
    DiscoveryMode,
    DiscoveryRequest,
    DiscoveryStatus,
    FixtureFetcher,
    NeutralDiscoveryConnector,
    ParseError,
    UnconfiguredFetcher,
    map_http_status,
    map_payload_error,
    parse_items,
)

_BOARD = {
    "items": [
        {"item_id": "x1", "views": 1000, "likes": 50, "saves": None, "hashtags": ["ai"]},
        {"item_id": "x2", "views": 300, "likes": None},
    ]
}


def _descriptor() -> ProviderDescriptor:
    return ProviderDescriptor(
        name="source.kittest",
        provider_type="SourceConnector",
        version="0.1.0",
        capabilities=["source.discover"],
        execution_location="local",
    )


def _connector(**kw) -> NeutralDiscoveryConnector:
    return NeutralDiscoveryConnector(
        descriptor=_descriptor(),
        connector_name="source.kittest",
        platform="kittest",
        collector_version="kit@0",
        source_confidence={DiscoveryMode.MANUAL: 0.75},
        **kw,
    )


def test_parse_items_preserves_null_metrics() -> None:
    snaps = parse_items(_BOARD, platform="test", collector_version="v", source_confidence=0.6)
    assert snaps[0].saves is None
    assert snaps[1].likes is None
    assert snaps[0].views == 1000


def test_parse_items_drift_raises() -> None:
    with pytest.raises(ParseError):
        parse_items(
            {"items": [{"views": 1}]}, platform="t", collector_version="v", source_confidence=0.6
        )


def test_map_payload_challenge_only_scans_message_fields() -> None:
    assert (
        map_payload_error({"error_message": "captcha"}).code
        == ConnectorErrorCode.CHALLENGE_REQUIRED
    )
    # 业务数据里的 risk/slider 子串不误判；有 items 即数据响应，直接放行
    assert map_payload_error({"items": [{"item_id": "sliderule"}]}) is None
    assert map_payload_error({"items": [], "risk_level": "low"}) is None
    assert map_http_status(429).code == ConnectorErrorCode.RATE_LIMITED


def test_connector_ok_empty_unconfigured() -> None:
    ok = _connector(fetcher=FixtureFetcher(default=_BOARD))
    assert ok.discover(DiscoveryRequest(DiscoveryMode.BOARD, "b")).status == DiscoveryStatus.OK

    empty = _connector(fetcher=FixtureFetcher(default={"items": []}))
    assert (
        empty.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "k")).status == DiscoveryStatus.EMPTY
    )

    uncfg = _connector(fetcher=UnconfiguredFetcher())
    r = uncfg.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "k"))
    assert r.status == DiscoveryStatus.UNCONFIGURED
    assert r.error_code == ConnectorErrorCode.APP_REVIEW_REQUIRED


def test_connector_manual_import_bypasses_circuit() -> None:
    clock = {"v": 0.0}
    breaker = CircuitBreaker(failure_threshold=1, cooldown_s=60, now_fn=lambda: clock["v"])
    breaker.record_failure()  # 打开
    c = _connector(fetcher=UnconfiguredFetcher(), breaker=breaker)
    assert c.import_manual(_BOARD).status == DiscoveryStatus.OK


def test_connector_challenge_routes_to_human() -> None:
    c = _connector(fetcher=FixtureFetcher(default={"error_message": "请完成滑块验证"}))
    r = c.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "k"))
    assert r.status == DiscoveryStatus.CHALLENGE
    assert r.error_code == ConnectorErrorCode.CHALLENGE_REQUIRED


def test_fetcher_error_propagates_as_failed() -> None:
    class Boom:
        def fetch(self, request):
            raise ConnectorError(ConnectorErrorCode.PLATFORM_TEMPORARY, "boom")

    c = _connector(fetcher=Boom())
    assert c.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "k")).status == DiscoveryStatus.FAILED
