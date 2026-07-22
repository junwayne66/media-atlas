"""yt-dlp 下载连接器（videoforge-connector-yt-dlp）。

自包含导入面：re-export 端口侧常用名，连接器用户无需再直接 import provider-sdk。
"""

from videoforge_connector_yt_dlp.connector import (
    CONNECTOR_NAME,
    YtDlpDownloadConnector,
    load_yt_dlp_descriptor,
)
from videoforge_connector_yt_dlp.cookies import (
    CookieResolver,
    ResolvedCookies,
    UnconfiguredCookieResolver,
)
from videoforge_connector_yt_dlp.runner import (
    PINNED_VERSION,
    RunResult,
    SubprocessYtDlpRunner,
    UnconfiguredYtDlpRunner,
    YtDlpNotAvailable,
    YtDlpRunner,
)
from videoforge_provider_sdk import (
    AcquisitionError,
    AcquisitionErrorCode,
    AcquisitionManifest,
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
    ResolvedSource,
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
    "ResolvedCookies",
    "ResolvedSource",
    "RunResult",
    "SubprocessYtDlpRunner",
    "UnconfiguredCookieResolver",
    "UnconfiguredYtDlpRunner",
    "YtDlpDownloadConnector",
    "YtDlpNotAvailable",
    "YtDlpRunner",
    "load_yt_dlp_descriptor",
    "resolve",
    "resolve_local_file",
    "resolve_url",
]
