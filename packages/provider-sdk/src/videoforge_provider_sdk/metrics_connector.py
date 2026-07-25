"""指标连接器端口 —— 回采平台表现快照（docs/modules/44 §10）。

端口让连接器**上报能力**（可用性/授权/能提供哪些字段/限流间隔）并**按年龄点抓一张快照**。

**红线（§10 null 语义）**：连接器只返回平台**实际提供**的指标，其余保持 None——Fake 只回放
录制值，**绝不把缺失字段编造成 0 或假数**。

**stop-condition**：真实平台官方数据 API（TikTok/抖音 Insights/Analytics）的 live 回采需真实
账号 + 应用审核 + 凭据。本端口**不触真实平台**：`UnconfiguredMetricsConnector` 诚实
UNCONFIGURED；`FakeMetricsConnector` 回放构造注入的快照，零网络（AST/grep 断言无
requests/httpx/socket）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import (
    AuthStatus,
    MetricField,
    MetricsConnectorCapability,
    PerformanceSnapshot,
    PublishPlatform,
)


class MetricsFetchStatus(StrEnum):
    OK = "OK"
    RATE_LIMITED = "RATE_LIMITED"  # 平台限流：稍后按 retry_after_seconds 重试
    UNCONFIGURED = "UNCONFIGURED"  # 未接入真实数据源（stop-condition）
    AUTH_REQUIRED = "AUTH_REQUIRED"  # 授权失效 → 人工
    NOT_FOUND = "NOT_FOUND"  # 帖子/指标不存在（尚未生效或已删）
    FAILED = "FAILED"


@dataclass(frozen=True)
class MetricsFetchResult:
    """一次抓取的结果。非 OK 时 `snapshot` 恒为 None（绝不返回半真数据）。"""

    status: MetricsFetchStatus
    snapshot: PerformanceSnapshot | None = None
    retry_after_seconds: int | None = None
    error_code: str | None = None


@runtime_checkable
class MetricsConnector(Protocol):
    """§10 指标连接器：上报能力 + 按年龄点抓快照。真实回采延后（stop-condition）。"""

    platform: PublishPlatform

    def capabilities(self) -> MetricsConnectorCapability: ...

    def fetch(
        self,
        *,
        platform_post_id: str,
        account_id: str,
        observed_at: datetime,
        age_hours: float,
    ) -> MetricsFetchResult: ...


class UnconfiguredMetricsConnector:
    """诚实占位：无真实数据源 → 上报不可用 + 未授权，fetch 恒 UNCONFIGURED（绝不编造指标）。"""

    def __init__(self, *, platform: PublishPlatform) -> None:
        self.platform = platform

    def capabilities(self) -> MetricsConnectorCapability:
        return MetricsConnectorCapability(
            platform=self.platform,
            available=False,
            auth_status=AuthStatus.UNAUTHORIZED,
            provided_fields=[],
            notes="未配置真实数据源（真实指标回采属 stop-condition）",
        )

    def fetch(
        self,
        *,
        platform_post_id: str,
        account_id: str,
        observed_at: datetime,
        age_hours: float,
    ) -> MetricsFetchResult:
        return MetricsFetchResult(
            status=MetricsFetchStatus.UNCONFIGURED,
            snapshot=None,
            error_code="UNCONFIGURED",
        )


class FakeMetricsConnector:
    """确定性 Fake：回放构造注入的快照（零网络、不触真实平台、保持 null 语义）。

    - 录制以 (platform_post_id, age_hours) 为键；命中 → OK + 快照的**深拷贝**（调用方改动不污染
      内部录制）；未命中 → NOT_FOUND，snapshot=None。
    - 注入 `rate_limited` → RATE_LIMITED + retry_after_seconds；`auth_required` → AUTH_REQUIRED；
      `fail` → FAILED。非 OK 一律 snapshot=None。
    - **绝不填充缺失指标**：回放的快照里 None 的字段照样 None（红线）。
    """

    def __init__(
        self,
        *,
        platform: PublishPlatform,
        recorded: dict[tuple[str, float], PerformanceSnapshot] | None = None,
        provided_fields: tuple[MetricField, ...] = (),
        min_seconds_between_calls: int = 0,
        available: bool = True,
        auth_status: AuthStatus = AuthStatus.AUTHORIZED,
        rate_limited: bool = False,
        retry_after_seconds: int = 60,
        auth_required: bool = False,
        fail: bool = False,
    ) -> None:
        self.platform = platform
        # 深拷贝入参，避免外部后续改动污染录制。
        self._recorded = {key: snap.model_copy(deep=True) for key, snap in (recorded or {}).items()}
        self._provided_fields = list(provided_fields)
        self._min_seconds = min_seconds_between_calls
        self._available = available
        self._auth_status = auth_status
        self._rate_limited = rate_limited
        self._retry_after = retry_after_seconds
        self._auth_required = auth_required
        self._fail = fail
        self.fetch_count = 0  # 供测试断言调用次数

    def capabilities(self) -> MetricsConnectorCapability:
        return MetricsConnectorCapability(
            platform=self.platform,
            available=self._available,
            auth_status=self._auth_status,
            provided_fields=list(self._provided_fields),
            min_seconds_between_calls=self._min_seconds,
            notes="Fake：非真实数据源，仅回放注入快照",
        )

    def fetch(
        self,
        *,
        platform_post_id: str,
        account_id: str,
        observed_at: datetime,
        age_hours: float,
    ) -> MetricsFetchResult:
        self.fetch_count += 1
        if self._auth_required:
            return MetricsFetchResult(
                MetricsFetchStatus.AUTH_REQUIRED, None, error_code="AUTH_REQUIRED"
            )
        if self._rate_limited:
            return MetricsFetchResult(
                MetricsFetchStatus.RATE_LIMITED,
                None,
                retry_after_seconds=self._retry_after,
                error_code="RATE_LIMITED",
            )
        if self._fail:
            return MetricsFetchResult(MetricsFetchStatus.FAILED, None, error_code="FAILED")
        snap = self._recorded.get((platform_post_id, age_hours))
        if snap is None:
            return MetricsFetchResult(MetricsFetchStatus.NOT_FOUND, None, error_code="NOT_FOUND")
        # 深拷贝返回：调用方改动不污染内部录制；null 字段照样 null。
        return MetricsFetchResult(MetricsFetchStatus.OK, snap.model_copy(deep=True))


__all__ = [
    "FakeMetricsConnector",
    "MetricsConnector",
    "MetricsFetchResult",
    "MetricsFetchStatus",
    "UnconfiguredMetricsConnector",
]
