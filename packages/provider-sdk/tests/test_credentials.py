"""共享凭据端口：不透明句柄 → 短时 cookie 文件；默认未配置即转人工，不静默匿名。"""

from pathlib import Path

import pytest

from videoforge_provider_sdk import (
    AcquisitionError,
    AcquisitionErrorCode,
    ResolvedCookies,
    UnconfiguredCookieResolver,
)


def test_resolved_cookies_holds_file_path() -> None:
    rc = ResolvedCookies(cookie_file=Path("/tmp/c.txt"))
    assert rc.cookie_file == Path("/tmp/c.txt")


def test_unconfigured_resolver_is_auth_required_not_silent_anonymous() -> None:
    with pytest.raises(AcquisitionError) as ei:
        UnconfiguredCookieResolver().resolve("cred_x")
    assert ei.value.code is AcquisitionErrorCode.AUTH_REQUIRED
    # 句柄值不得回显到异常里
    assert "cred_x" not in ei.value.detail
