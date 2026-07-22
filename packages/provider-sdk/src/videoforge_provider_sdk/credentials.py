"""凭据解析：credential_handle（不透明 id）→ 短时 Netscape cookie 文件。

跨下载连接器共用（yt-dlp / f2 都需要）。安全立场（README §4：UI/日志/TaskEnvelope
无明文平台凭据；macOS 用 Keychain）：

- 请求里只带不透明句柄，绝不带明文 Cookie。
- 解析出的 cookie 文件内容绝不进日志；只有文件路径进 argv（路径非机密，内容才是）。
- 默认 UnconfiguredCookieResolver：未接凭据存储。给了句柄却无法解析 → AUTH_REQUIRED
  （转人工提供凭据），而不是无声降级为匿名（否则会静默下载失败/触发风控）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from videoforge_provider_sdk.acquisition import AcquisitionErrorCode
from videoforge_provider_sdk.download_errors import AcquisitionError


@dataclass(frozen=True)
class ResolvedCookies:
    cookie_file: Path  # 短时 Netscape cookie 文件；内容绝不入日志


class CookieResolver(Protocol):
    def resolve(self, credential_handle: str) -> ResolvedCookies:
        """句柄 → 短时 cookie 文件；无法解析抛 AcquisitionError(AUTH_REQUIRED)。"""
        ...


class UnconfiguredCookieResolver:
    """默认：未接凭据存储。有句柄但解析不了即转人工，不静默匿名。"""

    def resolve(self, credential_handle: str) -> ResolvedCookies:
        raise AcquisitionError(
            AcquisitionErrorCode.AUTH_REQUIRED,
            "凭据存储未接线，无法解析 Cookie handle；请人工提供凭据或改用匿名/手工导入",
        )
