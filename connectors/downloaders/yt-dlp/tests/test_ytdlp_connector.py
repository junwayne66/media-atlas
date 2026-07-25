"""yt-dlp 连接器契约测试：argv 注入安全、下载→manifest、脱敏、Cookie handle、错误映射、
默认未配置不触网。全程用 FixtureYtDlpRunner，绝不跑真实二进制。"""

import hashlib

import pytest
from ytdlp_fixtures import FixtureYtDlpRunner, load_info_dict

from videoforge_connector_yt_dlp import (
    CONNECTOR_NAME,
    PINNED_VERSION,
    AcquisitionErrorCode,
    DownloadRequest,
    DownloadStatus,
    ResolvedCookies,
    ResolvedSource,
    UnconfiguredCookieResolver,
    YtDlpDownloadConnector,
    resolve_url,
)


def _tiktok_source() -> ResolvedSource:
    return resolve_url("https://www.tiktok.com/@demo_creator/video/7298765432109876543")


def _req(dest, **over) -> DownloadRequest:
    kwargs = dict(source=_tiktok_source(), dest_dir=dest, format_selector="best")
    kwargs.update(over)
    return DownloadRequest(**kwargs)


class _StubCookieResolver:
    """把句柄映射到一个真实存在的临时 cookie 文件；句柄值本身不进结果。"""

    def __init__(self, cookie_file) -> None:
        self._cookie_file = cookie_file
        self.seen_handles: list[str] = []

    def resolve(self, credential_handle: str) -> ResolvedCookies:
        self.seen_handles.append(credential_handle)
        return ResolvedCookies(cookie_file=self._cookie_file)


# —— 默认后端：不触网、不静默 ——


def test_default_connector_is_unconfigured(tmp_path) -> None:
    conn = YtDlpDownloadConnector()  # 默认 runner=Unconfigured
    result = conn.download(_req(tmp_path))
    assert result.status is DownloadStatus.UNCONFIGURED
    assert result.error_code is AcquisitionErrorCode.UNCONFIGURED
    assert result.media_path is None


def test_health_check_reports_unconfigured_by_default() -> None:
    assert YtDlpDownloadConnector().health_check().status is DownloadStatus.UNCONFIGURED


def test_descriptor_is_l4_download_provider() -> None:
    d = YtDlpDownloadConnector().descriptor
    assert d.name == CONNECTOR_NAME
    assert str(d.provider_type) == "DownloadProvider"
    assert str(d.isolation_level) == "L4"


def test_descriptor_pins_the_runner_version() -> None:
    # 锁定版本两处同步（runner.PINNED_VERSION ↔ descriptor）——升级漏改一处即失败
    d = YtDlpDownloadConnector().descriptor
    assert PINNED_VERSION in (d.license_notes or "")


# —— argv 构造：注入安全 ——


def test_build_argv_is_injection_safe(tmp_path) -> None:
    conn = YtDlpDownloadConnector()
    # 恶意格式串：即便以 - 开头也须作为 --format= 的值，不得变成新选项
    req = _req(tmp_path, format_selector="--exec=rm -rf ~")
    argv = conn.build_argv(req)
    assert "--format=--exec=rm -rf ~" in argv  # 整串是单 token
    assert "--exec=rm -rf ~" not in argv  # 没有裸的独立 token
    # URL 前有 -- 停止选项解析，且 URL 是最后一个 token
    assert argv[-2] == "--"
    assert argv[-1] == req.source.canonical_url
    # 无 shell 元字符拼接：argv 是纯列表，逐元素传子进程
    assert all(isinstance(t, str) for t in argv)


def test_build_argv_download_has_resume_and_idempotency_flags(tmp_path) -> None:
    argv = YtDlpDownloadConnector().build_argv(_req(tmp_path, resume=True))
    assert "--continue" in argv  # 断点续传
    assert "--no-overwrites" in argv  # 幂等
    assert "--no-playlist" in argv
    assert "--no-simulate" in argv
    assert f"--paths=home:{tmp_path}" in argv


def test_build_argv_no_resume(tmp_path) -> None:
    argv = YtDlpDownloadConnector().build_argv(_req(tmp_path, resume=False))
    assert "--no-continue" in argv
    assert "--continue" not in argv


def test_build_argv_probe_skips_download(tmp_path) -> None:
    argv = YtDlpDownloadConnector().build_argv(_req(tmp_path), skip_download=True)
    assert "--skip-download" in argv
    assert "--no-simulate" not in argv


def test_build_argv_rejects_unexpanded_short_link(tmp_path) -> None:
    short = resolve_url("https://vm.tiktok.com/ZMabc/")  # needs_expansion
    from videoforge_connector_yt_dlp import AcquisitionError

    with pytest.raises(AcquisitionError) as ei:
        YtDlpDownloadConnector().build_argv(DownloadRequest(source=short, dest_dir=tmp_path))
    assert ei.value.code is AcquisitionErrorCode.SOURCE_UNAVAILABLE


# —— 下载成功：manifest 可重放 + 脱敏 ——


def test_download_produces_replayable_manifest(tmp_path) -> None:
    runner = FixtureYtDlpRunner()
    conn = YtDlpDownloadConnector(runner=runner)
    result = conn.download(_req(tmp_path))

    assert result.status is DownloadStatus.OK
    assert result.media_path is not None and result.media_path.is_file()
    m = result.manifest
    assert m is not None
    assert m.tool == "yt-dlp"
    assert m.tool_version == "2025.01.15"  # 锁定/探测版本入 manifest
    assert m.container == "mp4"
    assert m.duration_s == 42.0
    assert m.resume_enabled is True
    # 输出哈希 = 真实文件哈希（可重放核验）
    expected = hashlib.sha256(b"FAKEMEDIA").hexdigest()
    assert m.output_sha256 == expected
    assert m.output_size == len(b"FAKEMEDIA")
    # 输入摘要稳定（同源同格式恒定）
    assert len(m.input_digest) == 64


def test_download_scrubs_credentials_from_raw_metadata(tmp_path) -> None:
    result = YtDlpDownloadConnector(runner=FixtureYtDlpRunner()).download(_req(tmp_path))
    blob = str(result.raw_metadata)
    # info-dict 里植入的 Cookie/Token 必须被抹掉
    assert "SECRET_SHOULD_BE_SCRUBBED" not in blob
    assert "SECRET_TOKEN_SHOULD_BE_SCRUBBED" not in blob
    assert "http_headers" not in result.raw_metadata
    # 技术字段保留
    assert result.raw_metadata["vcodec"] == "h264"


def test_download_is_idempotent_same_hash_on_rerun(tmp_path) -> None:
    conn = YtDlpDownloadConnector(runner=FixtureYtDlpRunner())
    a = conn.download(_req(tmp_path))
    b = conn.download(_req(tmp_path))  # 重跑：文件已存在，不覆盖
    assert a.manifest.output_sha256 == b.manifest.output_sha256
    assert a.manifest.input_digest == b.manifest.input_digest
    assert a.media_path == b.media_path


# —— Cookie handle：不透明、不入明文 ——


def test_cookie_handle_resolved_to_file_never_plaintext(tmp_path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape\n.tiktok.com\tTRUE\t/\tTRUE\t0\tsessionid\tSECRETCOOKIEVALUE\n"
    )
    resolver = _StubCookieResolver(cookie_file)
    runner = FixtureYtDlpRunner()
    conn = YtDlpDownloadConnector(runner=runner, cookie_resolver=resolver)

    result = conn.download(_req(tmp_path / "out", credential_handle="cred_tiktok_browser_1"))
    assert result.status is DownloadStatus.OK
    # 句柄被解析（resolver 收到），但只有 cookie 文件路径进 argv，句柄本身不进
    assert resolver.seen_handles == ["cred_tiktok_browser_1"]
    argv = runner.calls[0]
    assert f"--cookies={cookie_file}" in argv
    assert "cred_tiktok_browser_1" not in " ".join(argv)
    # cookie 文件内容（真正的机密）绝不出现在 argv
    assert "SECRETCOOKIEVALUE" not in " ".join(argv)


def test_anonymous_download_has_no_cookies_flag(tmp_path) -> None:
    runner = FixtureYtDlpRunner()
    YtDlpDownloadConnector(runner=runner).download(_req(tmp_path))  # 无 credential_handle
    assert not any(t.startswith("--cookies=") for t in runner.calls[0])


def test_unresolvable_cookie_handle_is_auth_required(tmp_path) -> None:
    # 默认 UnconfiguredCookieResolver：给了句柄却解析不了 → AUTH_REQUIRED（转人工，不静默匿名）
    conn = YtDlpDownloadConnector(
        runner=FixtureYtDlpRunner(), cookie_resolver=UnconfiguredCookieResolver()
    )
    result = conn.download(_req(tmp_path, credential_handle="cred_x"))
    assert result.status is DownloadStatus.AUTH_REQUIRED
    assert result.error_code is AcquisitionErrorCode.AUTH_REQUIRED
    assert result.media_path is None  # 未触发下载


# —— 失败映射：§12 + 挑战转人工 ——

_S, _C = DownloadStatus, AcquisitionErrorCode


@pytest.mark.parametrize(
    ("stderr", "status", "code"),
    [
        ("ERROR: please complete the captcha", _S.CHALLENGE, _C.CHALLENGE_REQUIRED),
        ("ERROR: Sign in to confirm your age", _S.AUTH_REQUIRED, _C.AUTH_REQUIRED),
        ("ERROR: HTTP Error 429: Too Many Requests", _S.FAILED, _C.RATE_LIMITED),
        ("ERROR: This video is private", _S.FAILED, _C.SOURCE_UNAVAILABLE),
        ("ERROR: Unable to extract video data", _S.FAILED, _C.CONNECTOR_SCHEMA_CHANGED),
    ],
)
def test_download_failure_maps_to_status_and_code(tmp_path, stderr, status, code) -> None:
    runner = FixtureYtDlpRunner(returncode=1, stderr=stderr)
    result = YtDlpDownloadConnector(runner=runner).download(_req(tmp_path))
    assert result.status is status
    assert result.error_code is code
    assert result.media_path is None


def test_non_json_stdout_is_schema_changed(tmp_path) -> None:
    runner = FixtureYtDlpRunner()
    runner._info = None  # type: ignore[assignment]
    # 直接构造一个返回非 JSON 的 runner

    class _Garbage:
        version = "2025.01.15"

        def run(self, argv, *, timeout_s):
            from videoforge_connector_yt_dlp import RunResult

            return RunResult(0, "<html>not json</html>", "")

    result = YtDlpDownloadConnector(runner=_Garbage()).download(_req(tmp_path))
    assert result.error_code is AcquisitionErrorCode.CONNECTOR_SCHEMA_CHANGED


def test_probe_returns_metadata_without_media(tmp_path) -> None:
    result = YtDlpDownloadConnector(runner=FixtureYtDlpRunner()).probe(_req(tmp_path))
    assert result.status is DownloadStatus.OK
    assert result.media_path is None
    assert result.raw_metadata["id"] == "7298765432109876543"


def test_locate_media_rejects_out_of_dest_absolute_path(tmp_path) -> None:
    # info-dict 给越界绝对路径（如 /etc/hosts）时，绝不返回它——回退到 dest 内的产物
    info = load_info_dict()
    info["requested_downloads"] = [{"filepath": "/etc/hosts"}]
    info["filepath"] = "/etc/passwd"
    result = YtDlpDownloadConnector(runner=FixtureYtDlpRunner(info=info)).download(_req(tmp_path))
    assert result.status is DownloadStatus.OK
    assert result.media_path is not None
    assert str(result.media_path.resolve()).startswith(str(tmp_path.resolve()))
    assert result.media_path.name == "7298765432109876543.mp4"
