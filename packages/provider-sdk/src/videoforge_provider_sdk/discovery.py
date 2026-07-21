"""发现连接器端口（docs/modules/40 §2，docs/architecture/30 §9）。

平台连接器实现本协议，只进出结构化合同（TrendItemSnapshot），业务模块
不依赖任何第三方项目的内部结构（README §4 规则 2）。空结果必须可诊断——
DiscoveryStatus 区分「采集成功但无数据（EMPTY）」与「采集失败（FAILED）」，
不得悄悄返回空榜单（40 §9/§10）。
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import ProviderDescriptor, TrendItemSnapshot


class DiscoveryMode(StrEnum):
    KEYWORD = "keyword"
    ACCOUNT = "account"
    BOARD = "board"  # 榜单/话题页
    MANUAL = "manual"  # 手工导入，始终可用的回退


class DiscoveryStatus(StrEnum):
    OK = "ok"  # 有数据
    EMPTY = "empty"  # 采集成功但无数据（可诊断的空，≠失败）
    FAILED = "failed"  # 采集失败
    UNCONFIGURED = "unconfigured"  # 需凭据/授权，未配置（停止条件）
    CHALLENGE = "challenge"  # 验证码/风控，转人工（不尝试绕过）


class ConnectorErrorCode(StrEnum):
    """外部错误统一映射（docs/implementation/51 §12）。"""

    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_SCOPE_MISSING = "AUTH_SCOPE_MISSING"
    APP_REVIEW_REQUIRED = "APP_REVIEW_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    PLATFORM_TEMPORARY = "PLATFORM_TEMPORARY"
    PLATFORM_REJECTED = "PLATFORM_REJECTED"
    MEDIA_INVALID = "MEDIA_INVALID"
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
    CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
    SELECTOR_CHANGED = "SELECTOR_CHANGED"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class DiscoveryRequest:
    mode: DiscoveryMode
    query: str  # keyword / account id / board id；MANUAL 时可为标识
    platform: str = "douyin"
    region: str | None = None
    locale: str | None = None
    limit: int = 20


@dataclass
class DiscoveryResult:
    status: DiscoveryStatus
    connector: str
    mode: DiscoveryMode
    snapshots: list[TrendItemSnapshot] = field(default_factory=list)
    error_code: ConnectorErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == DiscoveryStatus.OK


# CHALLENGE/UNCONFIGURED 是独立 DiscoveryStatus；其余错误码归入 FAILED
_STATUS_BY_CODE: dict[ConnectorErrorCode, DiscoveryStatus] = {
    ConnectorErrorCode.CHALLENGE_REQUIRED: DiscoveryStatus.CHALLENGE,
    ConnectorErrorCode.APP_REVIEW_REQUIRED: DiscoveryStatus.UNCONFIGURED,
    ConnectorErrorCode.AUTH_EXPIRED: DiscoveryStatus.UNCONFIGURED,
    ConnectorErrorCode.AUTH_SCOPE_MISSING: DiscoveryStatus.UNCONFIGURED,
}


def status_for_error(code: ConnectorErrorCode) -> DiscoveryStatus:
    return _STATUS_BY_CODE.get(code, DiscoveryStatus.FAILED)


@runtime_checkable
class DiscoveryConnector(Protocol):
    descriptor: ProviderDescriptor

    def discover(self, request: DiscoveryRequest) -> DiscoveryResult: ...

    def health_check(self) -> DiscoveryResult: ...
