"""f2 下载连接器（videoforge-connector-f2）。

自包含导入面：re-export 端口侧常用名，连接器用户无需再直接 import provider-sdk。
"""

from videoforge_connector_f2.connector import (
    CONNECTOR_NAME,
    F2DownloadConnector,
    load_f2_descriptor,
)
from videoforge_connector_f2.runner import (
    PINNED_VERSION,
    F2NotAvailable,
    F2Runner,
    RunResult,
    SubprocessF2Runner,
    UnconfiguredF2Runner,
)
from videoforge_provider_sdk import (
    AcquisitionError,
    AcquisitionErrorCode,
    AcquisitionManifest,
    CookieResolver,
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
    ResolvedCookies,
    ResolvedSource,
    UnconfiguredCookieResolver,
    resolve,
    resolve_local_file,
    resolve_url,
)

__all__ = [
    "CONNECTOR_NAME",
    "PINNED_VERSION",
    "AcquisitionError",
    "AcquisitionErrorCode",
    "AcquisitionManifest",
    "CookieResolver",
    "DownloadRequest",
    "DownloadResult",
    "DownloadStatus",
    "F2DownloadConnector",
    "F2NotAvailable",
    "F2Runner",
    "ResolvedCookies",
    "ResolvedSource",
    "RunResult",
    "SubprocessF2Runner",
    "UnconfiguredCookieResolver",
    "UnconfiguredF2Runner",
    "load_f2_descriptor",
    "resolve",
    "resolve_local_file",
    "resolve_url",
]
