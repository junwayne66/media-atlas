"""下载优先级 + 回退编排：按平台择优、失败回退、CHALLENGE/AUTH 终止不跨 provider 绕过。"""

from pathlib import Path

from videoforge_provider_sdk import (
    AcquisitionErrorCode,
    DownloadRequest,
    DownloadResult,
    DownloadRouter,
    DownloadStatus,
    ResolvedSource,
)


class _FakeConn:
    def __init__(self, name: str, result: DownloadResult) -> None:
        self._name = name
        self._result = result
        self.calls = 0

    def download(self, request: DownloadRequest) -> DownloadResult:
        self.calls += 1
        return self._result


def _res(status: DownloadStatus, code: AcquisitionErrorCode | None = None) -> DownloadResult:
    return DownloadResult(status=status, connector="x", error_code=code)


def _req(platform: str) -> DownloadRequest:
    src = ResolvedSource(
        platform=platform, content_id="1", canonical_url="https://x/1", raw_input="x"
    )
    return DownloadRequest(source=src, dest_dir=Path("/tmp"))


def _ok() -> DownloadResult:
    return _res(DownloadStatus.OK)


def _failed(code=AcquisitionErrorCode.SOURCE_UNAVAILABLE) -> DownloadResult:
    return _res(DownloadStatus.FAILED, code)


def _unconfigured() -> DownloadResult:
    return _res(DownloadStatus.UNCONFIGURED, AcquisitionErrorCode.UNCONFIGURED)


def test_chain_reflects_platform_priority_filtered_to_registered() -> None:
    f2, yt = _FakeConn("f2", _ok()), _FakeConn("yt", _ok())
    router = DownloadRouter({"download.f2": f2, "download.yt_dlp": yt})
    assert router.chain_for("douyin") == ["download.f2", "download.yt_dlp"]  # 抖音 f2 优先
    assert router.chain_for("tiktok") == ["download.yt_dlp", "download.f2"]  # TikTok yt-dlp 优先
    # 只注册了 yt-dlp 时，抖音链里 f2 被过滤掉
    only_yt = DownloadRouter({"download.yt_dlp": yt})
    assert only_yt.chain_for("douyin") == ["download.yt_dlp"]


def test_first_success_short_circuits_second_not_called() -> None:
    f2, yt = _FakeConn("f2", _ok()), _FakeConn("yt", _ok())
    out = DownloadRouter({"download.f2": f2, "download.yt_dlp": yt}).download(_req("douyin"))
    assert out.ok
    assert f2.calls == 1
    assert yt.calls == 0  # 首个成功即短路
    assert out.manual_fallback is False
    assert [a.connector for a in out.attempts] == ["download.f2"]


def test_falls_back_on_non_terminal_failure() -> None:
    f2 = _FakeConn("f2", _failed(AcquisitionErrorCode.CONNECTOR_SCHEMA_CHANGED))
    yt = _FakeConn("yt", _ok())
    out = DownloadRouter({"download.f2": f2, "download.yt_dlp": yt}).download(_req("douyin"))
    assert out.ok
    assert f2.calls == 1 and yt.calls == 1  # f2 失效 → 回退 yt-dlp 成功
    assert [a.connector for a in out.attempts] == ["download.f2", "download.yt_dlp"]
    assert out.manual_fallback is False


def test_unconfigured_falls_through_to_next() -> None:
    f2, yt = _FakeConn("f2", _unconfigured()), _FakeConn("yt", _ok())
    out = DownloadRouter({"download.f2": f2, "download.yt_dlp": yt}).download(_req("douyin"))
    assert out.ok and yt.calls == 1


def test_challenge_is_terminal_does_not_try_next_provider() -> None:
    # 关键安全语义：f2 遇验证码 → 转人工，绝不换 yt-dlp 去绕过平台风控
    f2 = _FakeConn("f2", _res(DownloadStatus.CHALLENGE, AcquisitionErrorCode.CHALLENGE_REQUIRED))
    yt = _FakeConn("yt", _ok())
    out = DownloadRouter({"download.f2": f2, "download.yt_dlp": yt}).download(_req("douyin"))
    assert out.result.status is DownloadStatus.CHALLENGE
    assert f2.calls == 1
    assert yt.calls == 0  # 不回退
    assert out.manual_fallback is False


def test_auth_required_is_terminal_no_fallback() -> None:
    f2 = _FakeConn("f2", _res(DownloadStatus.AUTH_REQUIRED, AcquisitionErrorCode.AUTH_REQUIRED))
    yt = _FakeConn("yt", _ok())
    out = DownloadRouter({"download.f2": f2, "download.yt_dlp": yt}).download(_req("douyin"))
    assert out.result.status is DownloadStatus.AUTH_REQUIRED
    assert yt.calls == 0


def test_all_fail_falls_back_to_manual() -> None:
    f2, yt = _FakeConn("f2", _failed()), _FakeConn("yt", _failed())
    out = DownloadRouter({"download.f2": f2, "download.yt_dlp": yt}).download(_req("douyin"))
    assert out.manual_fallback is True
    assert not out.ok
    assert len(out.attempts) == 2  # 两个都试过了


def test_unknown_platform_goes_straight_to_manual() -> None:
    out = DownloadRouter({}).download(_req("bilibili"))
    assert out.manual_fallback is True
    assert out.result.error_code is AcquisitionErrorCode.UNCONFIGURED
    assert out.attempts == []


def test_manual_platform_has_no_download_chain() -> None:
    out = DownloadRouter({}).download(_req("manual"))
    assert out.manual_fallback is True
    assert out.attempts == []
