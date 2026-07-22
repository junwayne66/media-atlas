"""可复用发现连接器编排（docs/architecture/30 §9）。平台无关。

各平台连接器（douyin/tiktok/...）用平台配置薄接入即可：熔断 → fetcher 取原始
响应 → payload 错误识别 → parser 归一化 → 空/失败可诊断。手工导入不走 fetcher/
熔断，始终可用。验证码/风控 → CHALLENGE，转人工，不绕过。
"""

from typing import Any

from videoforge_contracts import ProviderDescriptor
from videoforge_provider_sdk.circuit import CircuitBreaker
from videoforge_provider_sdk.connector_errors import ConnectorError, map_payload_error
from videoforge_provider_sdk.discovery import (
    DiscoveryMode,
    DiscoveryRequest,
    DiscoveryResult,
    DiscoveryStatus,
    status_for_error,
)
from videoforge_provider_sdk.fetcher import DiscoveryFetcher, UnconfiguredFetcher
from videoforge_provider_sdk.neutral_parser import parse_items

CANARY_KEYWORD = "__canary__"
_DEFAULT_SOURCE_CONFIDENCE = 0.6


class NeutralDiscoveryConnector:
    """消费平台中性响应的发现连接器基类。平台差异仅在构造配置。"""

    def __init__(
        self,
        *,
        descriptor: ProviderDescriptor,
        connector_name: str,
        platform: str,
        collector_version: str,
        source_confidence: dict[DiscoveryMode, float] | None = None,
        fetcher: DiscoveryFetcher | None = None,
        breaker: CircuitBreaker | None = None,
        canary_keyword: str = CANARY_KEYWORD,
    ) -> None:
        self.descriptor = descriptor
        self._name = connector_name
        self._platform = platform
        self._collector_version = collector_version
        self._source_confidence = source_confidence or {}
        self._fetcher = fetcher or UnconfiguredFetcher()
        self._breaker = breaker or CircuitBreaker()
        self._canary_keyword = canary_keyword

    def _confidence(self, mode: DiscoveryMode) -> float:
        return self._source_confidence.get(mode, _DEFAULT_SOURCE_CONFIDENCE)

    def _result(
        self,
        status: DiscoveryStatus,
        mode: DiscoveryMode,
        *,
        snapshots: list | None = None,
        error_code: Any = None,
        detail: str | None = None,
    ) -> DiscoveryResult:
        return DiscoveryResult(
            status=status,
            connector=self._name,
            mode=mode,
            snapshots=snapshots or [],
            error_code=error_code,
            detail=detail,
        )

    def import_manual(self, response: dict[str, Any]) -> DiscoveryResult:
        """手工导入：归一化 JSON → snapshots。始终可用，不走 fetcher/熔断。"""
        try:
            snapshots = parse_items(
                response,
                platform=self._platform,
                collector_version=self._collector_version,
                source_confidence=self._confidence(DiscoveryMode.MANUAL),
            )
        except ConnectorError as exc:
            return self._result(
                DiscoveryStatus.FAILED, DiscoveryMode.MANUAL, error_code=exc.code, detail=exc.detail
            )
        status = DiscoveryStatus.OK if snapshots else DiscoveryStatus.EMPTY
        return self._result(status, DiscoveryMode.MANUAL, snapshots=snapshots)

    def discover(self, request: DiscoveryRequest) -> DiscoveryResult:
        if request.mode == DiscoveryMode.MANUAL:
            raise ValueError("MANUAL 模式请用 import_manual(response)")
        if not self._breaker.allow_request():
            return self._result(
                DiscoveryStatus.FAILED,
                request.mode,
                detail="熔断打开，暂不采集（等待冷却）",
            )
        self._breaker.reserve_probe()
        try:
            raw = self._fetcher.fetch(request)
        except ConnectorError as exc:
            self._breaker.record_failure()
            return self._result(
                status_for_error(exc.code), request.mode, error_code=exc.code, detail=exc.detail
            )

        # 200 响应体里也可能夹带验证码/风控或业务错误——解析前先识别，转人工不绕过
        payload_error = map_payload_error(raw)
        if payload_error is not None:
            self._breaker.record_failure()
            return self._result(
                status_for_error(payload_error.code),
                request.mode,
                error_code=payload_error.code,
                detail=payload_error.detail,
            )

        try:
            snapshots = parse_items(
                raw,
                platform=self._platform,
                collector_version=self._collector_version,
                source_confidence=self._confidence(request.mode),
            )
        except ConnectorError as exc:
            # 解析失败（结构漂移）也计入熔断——连续漂移应停采并标红
            self._breaker.record_failure()
            return self._result(
                status_for_error(exc.code), request.mode, error_code=exc.code, detail=exc.detail
            )

        self._breaker.record_success()
        # 采集成功：有数据 OK，无数据 EMPTY（可诊断的空，不是失败）
        status = DiscoveryStatus.OK if snapshots else DiscoveryStatus.EMPTY
        return self._result(status, request.mode, snapshots=snapshots)

    def health_check(self) -> DiscoveryResult:
        """Canary：用固定关键词探测（40 §9）。未配置 → UNCONFIGURED，可 UI 标红。"""
        return self.discover(
            DiscoveryRequest(mode=DiscoveryMode.KEYWORD, query=self._canary_keyword, limit=1)
        )
