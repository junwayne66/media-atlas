"""连接器编排：手工导入始终可用、空 vs 失败可诊断、未配置=停止条件、
验证码转人工、熔断周期、canary。全链路不触网。"""

from fixtures_helper import load_fixture

from videoforge_connector_douyin import (
    CANARY_KEYWORD,
    ConnectorError,
    DouyinDiscoveryConnector,
    FixtureFetcher,
    UnconfiguredFetcher,
)
from videoforge_provider_sdk import (
    CircuitBreaker,
    ConnectorErrorCode,
    DiscoveryMode,
    DiscoveryRequest,
    DiscoveryStatus,
)


class FailingFetcher:
    def __init__(self, error):
        self._error = error

    def fetch(self, request):
        raise self._error


def _clock():
    t = {"v": 0.0}
    return t, (lambda: t["v"])


def test_descriptor_loads_as_l4() -> None:
    c = DouyinDiscoveryConnector()
    assert c.descriptor.name == "source.douyin"
    assert c.descriptor.isolation_level == "L4"
    assert "source.discover" in c.descriptor.capabilities


def test_manual_import_always_available() -> None:
    c = DouyinDiscoveryConnector()  # 默认 UnconfiguredFetcher
    result = c.import_manual(load_fixture("manual_import.json"))
    assert result.status == DiscoveryStatus.OK
    assert result.mode == DiscoveryMode.MANUAL
    assert result.snapshots[0].item_id == "dy-manual-1"
    assert result.snapshots[0].source_confidence == 0.75  # 手工来源可信度


def test_manual_import_empty_is_diagnosable_empty() -> None:
    c = DouyinDiscoveryConnector()
    result = c.import_manual(load_fixture("empty_response.json"))
    assert result.status == DiscoveryStatus.EMPTY  # 不是 FAILED
    assert result.snapshots == []


def test_manual_import_malformed_is_failed() -> None:
    c = DouyinDiscoveryConnector()
    result = c.import_manual(load_fixture("drift_response.json"))
    assert result.status == DiscoveryStatus.FAILED
    assert result.error_code == ConnectorErrorCode.SELECTOR_CHANGED


def test_discover_with_fixture_fetcher_ok() -> None:
    c = DouyinDiscoveryConnector(
        fetcher=FixtureFetcher(default=load_fixture("board_response.json"))
    )
    result = c.discover(DiscoveryRequest(DiscoveryMode.BOARD, "hot-board"))
    assert result.status == DiscoveryStatus.OK
    assert len(result.snapshots) == 2


def test_discover_empty_is_not_failure() -> None:
    c = DouyinDiscoveryConnector(
        fetcher=FixtureFetcher(default=load_fixture("empty_response.json"))
    )
    result = c.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "obscure"))
    assert result.status == DiscoveryStatus.EMPTY  # 采集成功但无数据
    assert result.error_code is None


def test_unconfigured_is_stop_condition_not_empty() -> None:
    c = DouyinDiscoveryConnector(fetcher=UnconfiguredFetcher())
    result = c.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "ai"))
    assert result.status == DiscoveryStatus.UNCONFIGURED  # 不静默返回空榜单
    assert result.error_code == ConnectorErrorCode.APP_REVIEW_REQUIRED


def test_challenge_payload_routes_to_human() -> None:
    fetcher = FixtureFetcher(default=load_fixture("challenge_response.json"))
    c = DouyinDiscoveryConnector(fetcher=fetcher)
    result = c.discover(DiscoveryRequest(DiscoveryMode.KEYWORD, "ai"))
    assert result.status == DiscoveryStatus.CHALLENGE  # 转人工，不绕过
    assert result.error_code == ConnectorErrorCode.CHALLENGE_REQUIRED


def test_manual_import_works_even_when_circuit_open() -> None:
    box, now = _clock()
    breaker = CircuitBreaker(failure_threshold=1, cooldown_s=60, now_fn=now)
    breaker.record_failure()  # 打开熔断
    c = DouyinDiscoveryConnector(fetcher=UnconfiguredFetcher(), breaker=breaker)
    # 手工导入不受熔断影响
    result = c.import_manual(load_fixture("manual_import.json"))
    assert result.status == DiscoveryStatus.OK


def test_circuit_opens_after_failures_then_recovers() -> None:
    box, now = _clock()
    breaker = CircuitBreaker(failure_threshold=2, cooldown_s=60, now_fn=now)
    err = FailingFetcher(ConnectorError(ConnectorErrorCode.PLATFORM_TEMPORARY, "boom"))
    c = DouyinDiscoveryConnector(fetcher=err, breaker=breaker)
    req = DiscoveryRequest(DiscoveryMode.KEYWORD, "ai")

    assert c.discover(req).error_code == ConnectorErrorCode.PLATFORM_TEMPORARY
    assert c.discover(req).error_code == ConnectorErrorCode.PLATFORM_TEMPORARY
    # 阈值到 → 熔断打开，下次不再打 fetcher，返回熔断态
    blocked = c.discover(req)
    assert blocked.status == DiscoveryStatus.FAILED
    assert "熔断" in blocked.detail

    box["v"] += 60  # 冷却结束 → 半开，恢复探测
    healthy = DouyinDiscoveryConnector(
        fetcher=FixtureFetcher(default=load_fixture("board_response.json")), breaker=breaker
    )
    assert healthy.discover(req).status == DiscoveryStatus.OK


def test_canary_health_check_unconfigured() -> None:
    c = DouyinDiscoveryConnector()  # UnconfiguredFetcher 默认
    health = c.health_check()
    assert health.status == DiscoveryStatus.UNCONFIGURED

    healthy = DouyinDiscoveryConnector(
        fetcher=FixtureFetcher(default=load_fixture("board_response.json"))
    )
    probe = healthy.health_check()
    assert probe.status == DiscoveryStatus.OK
    # canary 用固定关键词
    assert CANARY_KEYWORD == "__canary__"
