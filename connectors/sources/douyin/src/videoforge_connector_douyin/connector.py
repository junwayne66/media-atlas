"""抖音发现连接器（docs/architecture/30 §9）。

编排：熔断 → fetcher 取原始响应 → parser 归一化 → 空/失败可诊断。手工导入
不走 fetcher/熔断，始终可用（连接器失效时的可靠回退）。遇验证码/风控返回
CHALLENGE，转人工，不尝试绕过。
"""

from pathlib import Path
from typing import Any

from videoforge_connector_douyin.error_mapping import ConnectorError, map_payload_error
from videoforge_connector_douyin.fetcher import DouyinFetcher, UnconfiguredFetcher
from videoforge_connector_douyin.parser import parse_items
from videoforge_contracts import ProviderDescriptor
from videoforge_provider_sdk import (
    CircuitBreaker,
    DiscoveryMode,
    DiscoveryRequest,
    DiscoveryResult,
    DiscoveryStatus,
    load_descriptor,
    status_for_error,
)

CONNECTOR_NAME = "source.douyin"
COLLECTOR_VERSION = "douyin-collector@0.1.0"
CANARY_KEYWORD = "__canary__"

# 每模式的来源可信度（40 §3.2）：手工人工收集 vs 公开信号抓取
_SOURCE_CONFIDENCE = {
    DiscoveryMode.MANUAL: 0.75,
    DiscoveryMode.KEYWORD: 0.6,
    DiscoveryMode.ACCOUNT: 0.6,
    DiscoveryMode.BOARD: 0.6,
}


def load_douyin_descriptor() -> ProviderDescriptor:
    # connector.py → videoforge_connector_douyin → src → douyin（含 descriptor.yaml）
    return load_descriptor(Path(__file__).resolve().parents[2] / "descriptor.yaml")


class DouyinDiscoveryConnector:
    def __init__(
        self,
        descriptor: ProviderDescriptor | None = None,
        *,
        fetcher: DouyinFetcher | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.descriptor = descriptor or load_douyin_descriptor()
        self._fetcher = fetcher or UnconfiguredFetcher()
        self._breaker = breaker or CircuitBreaker()

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
            connector=CONNECTOR_NAME,
            mode=mode,
            snapshots=snapshots or [],
            error_code=error_code,
            detail=detail,
        )

    def import_manual(
        self, response: dict[str, Any], *, request: DiscoveryRequest | None = None
    ) -> DiscoveryResult:
        """手工导入：归一化 JSON → snapshots。始终可用，不走 fetcher/熔断。"""
        req = request or DiscoveryRequest(mode=DiscoveryMode.MANUAL, query="manual")
        try:
            snapshots = parse_items(
                response,
                platform=req.platform,
                collector_version=COLLECTOR_VERSION,
                source_confidence=_SOURCE_CONFIDENCE[DiscoveryMode.MANUAL],
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
                error_code=None,
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
                platform=request.platform,
                collector_version=COLLECTOR_VERSION,
                source_confidence=_SOURCE_CONFIDENCE.get(request.mode, 0.6),
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
            DiscoveryRequest(mode=DiscoveryMode.KEYWORD, query=CANARY_KEYWORD, limit=1)
        )
