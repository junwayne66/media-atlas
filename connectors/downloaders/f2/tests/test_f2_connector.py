"""f2 连接器契约测试：argv 注入安全、下载→manifest、脱敏、Cookie handle、平台限定、
默认未配置不触网。全程用 FixtureF2Runner，绝不跑真实二进制。"""

import hashlib

import pytest
from f2_fixtures import FixtureF2Runner

from videoforge_connector_f2 import (
    CONNECTOR_NAME,
    PINNED_VERSION,
    AcquisitionError,
    AcquisitionErrorCode,
    DownloadRequest,
    DownloadStatus,
    F2DownloadConnector,
    ResolvedCookies,
    ResolvedSource,
    UnconfiguredCookieResolver,
    resolve_url,
)


def _douyin_source() -> ResolvedSource:
    return resolve_url("https://www.douyin.com/video/7412345678901234567")


def _req(dest, source=None, **over) -> DownloadRequest:
    kwargs = dict(source=source or _douyin_source(), dest_dir=dest, format_selector="best")
    kwargs.update(over)
    return DownloadRequest(**kwargs)


class _StubCookieResolver:
    def __init__(self, cookie_file) -> None:
        self._cookie_file = cookie_file
        self.seen_handles: list[str] = []

    def resolve(self, credential_handle: str) -> ResolvedCookies:
        self.seen_handles.append(credential_handle)
        return ResolvedCookies(cookie_file=self._cookie_file)


# —— 默认后端：不触网、不静默 ——


def test_default_connector_is_unconfigured(tmp_path) -> None:
    result = F2DownloadConnector().download(_req(tmp_path))
    assert result.status is DownloadStatus.UNCONFIGURED
    assert result.error_code is AcquisitionErrorCode.UNCONFIGURED
    assert result.media_path is None


def test_health_check_unconfigured_by_default() -> None:
    assert F2DownloadConnector().health_check().status is DownloadStatus.UNCONFIGURED


def test_descriptor_is_l4_download_provider_for_douyin_tiktok() -> None:
    d = F2DownloadConnector().descriptor
    assert d.name == CONNECTOR_NAME
    assert str(d.provider_type) == "DownloadProvider"
    assert str(d.isolation_level) == "L4"
    assert set(d.platforms) == {"douyin", "tiktok"}


def test_descriptor_pins_the_runner_version() -> None:
    assert PINNED_VERSION in (F2DownloadConnector().descriptor.license_notes or "")


# —— argv 构造：注入安全 + 平台子命令 ——


def test_build_argv_is_injection_safe(tmp_path) -> None:
    req = _req(tmp_path)
    req = DownloadRequest(
        source=ResolvedSource(
            platform="douyin",
            content_id="7412345678901234567",
            canonical_url="https://www.douyin.com/video/7412345678901234567; rm -rf ~",
            raw_input="x",
        ),
        dest_dir=tmp_path,
    )
    argv = F2DownloadConnector().build_argv(req)
    # 恶意 URL 整体作为 --url= 的值（单 token），不产生裸 token / shell 拼接
    assert any(t.startswith("--url=") and "rm -rf ~" in t for t in argv)
    assert "rm -rf ~" not in [t for t in argv if not t.startswith("--url=")]
    assert argv[0] == "dy"  # 抖音子命令
    assert all(isinstance(t, str) for t in argv)


def test_build_argv_tiktok_uses_tk_subcommand(tmp_path) -> None:
    src = resolve_url("https://www.tiktok.com/@u/video/7298765432109876543")
    argv = F2DownloadConnector().build_argv(_req(tmp_path, source=src))
    assert argv[0] == "tk"


def test_build_argv_probe_adds_no_download(tmp_path) -> None:
    argv = F2DownloadConnector().build_argv(_req(tmp_path), skip_download=True)
    assert "--no-download" in argv


def test_build_argv_rejects_unsupported_platform(tmp_path) -> None:
    src = ResolvedSource(
        platform="youtube", content_id="a", canonical_url="https://youtu.be/a", raw_input="x"
    )
    with pytest.raises(AcquisitionError) as ei:
        F2DownloadConnector().build_argv(_req(tmp_path, source=src))
    assert ei.value.code is AcquisitionErrorCode.SOURCE_UNAVAILABLE


def test_build_argv_rejects_manual(tmp_path) -> None:
    src = ResolvedSource(
        platform="manual", content_id="a.mp4", canonical_url="/a.mp4", raw_input="x"
    )
    with pytest.raises(AcquisitionError):
        F2DownloadConnector().build_argv(_req(tmp_path, source=src))


# —— 下载成功：manifest 可重放 + 脱敏 ——


def test_download_produces_replayable_manifest(tmp_path) -> None:
    result = F2DownloadConnector(runner=FixtureF2Runner()).download(_req(tmp_path))
    assert result.status is DownloadStatus.OK
    assert result.media_path is not None and result.media_path.is_file()
    m = result.manifest
    assert m.tool == "f2"
    assert m.tool_version == "0.0.1.7"
    assert m.provider == "download.f2"
    assert m.container == "mp4"
    assert m.duration_s == 35.5
    assert m.output_sha256 == hashlib.sha256(b"FAKEF2MEDIA").hexdigest()
    assert len(m.input_digest) == 64


def test_download_scrubs_credentials(tmp_path) -> None:
    result = F2DownloadConnector(runner=FixtureF2Runner()).download(_req(tmp_path))
    blob = str(result.raw_metadata)
    assert "SECRET_SHOULD_BE_SCRUBBED" not in blob
    assert "SECRET_TOKEN_SHOULD_BE_SCRUBBED" not in blob
    assert "http_headers" not in result.raw_metadata
    assert "cookie" not in result.raw_metadata
    assert "token" not in result.raw_metadata
    assert result.raw_metadata["vcodec"] == "h264"  # 技术字段保留


def test_download_is_idempotent(tmp_path) -> None:
    conn = F2DownloadConnector(runner=FixtureF2Runner())
    a = conn.download(_req(tmp_path))
    b = conn.download(_req(tmp_path))
    assert a.manifest.output_sha256 == b.manifest.output_sha256
    assert a.media_path == b.media_path


# —— Cookie handle：不透明、不入明文 ——


def test_cookie_handle_never_plaintext(tmp_path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape\n.douyin.com\tTRUE\t/\tTRUE\t0\tsessionid\tSECRETVAL\n")
    resolver = _StubCookieResolver(cookie_file)
    runner = FixtureF2Runner()
    conn = F2DownloadConnector(runner=runner, cookie_resolver=resolver)
    result = conn.download(_req(tmp_path / "out", credential_handle="cred_douyin_1"))
    assert result.status is DownloadStatus.OK
    assert resolver.seen_handles == ["cred_douyin_1"]
    argv = runner.calls[0]
    assert f"--cookie-file={cookie_file}" in argv
    assert "cred_douyin_1" not in " ".join(argv)
    assert "SECRETVAL" not in " ".join(argv)


def test_unresolvable_cookie_handle_is_auth_required(tmp_path) -> None:
    conn = F2DownloadConnector(
        runner=FixtureF2Runner(), cookie_resolver=UnconfiguredCookieResolver()
    )
    result = conn.download(_req(tmp_path, credential_handle="cred_x"))
    assert result.status is DownloadStatus.AUTH_REQUIRED
    assert result.media_path is None


# —— 失败映射：§12 + 挑战转人工（含中文签名）——

_S, _C = DownloadStatus, AcquisitionErrorCode


@pytest.mark.parametrize(
    ("stderr", "status", "code"),
    [
        ("检测到滑块验证，请完成安全验证", _S.CHALLENGE, _C.CHALLENGE_REQUIRED),
        ("需要登录后才能访问", _S.AUTH_REQUIRED, _C.AUTH_REQUIRED),
        ("请求过于频繁，请稍后再试", _S.FAILED, _C.RATE_LIMITED),
        ("作品不存在或已删除", _S.FAILED, _C.SOURCE_UNAVAILABLE),
        ("unable to extract play_addr", _S.FAILED, _C.CONNECTOR_SCHEMA_CHANGED),
    ],
)
def test_failure_maps_chinese_signatures(tmp_path, stderr, status, code) -> None:
    runner = FixtureF2Runner(returncode=1, stderr=stderr)
    result = F2DownloadConnector(runner=runner).download(_req(tmp_path))
    assert result.status is status
    assert result.error_code is code


def test_probe_returns_metadata_without_media(tmp_path) -> None:
    result = F2DownloadConnector(runner=FixtureF2Runner()).probe(_req(tmp_path))
    assert result.status is DownloadStatus.OK
    assert result.media_path is None
    assert result.raw_metadata["id"] == "7412345678901234567"
