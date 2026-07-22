"""获取端口：输入摘要可重放、错误码→状态映射、DownloadResult 便捷属性。"""

from datetime import UTC, datetime

from videoforge_provider_sdk.acquisition import (
    AcquisitionErrorCode,
    AcquisitionManifest,
    DownloadResult,
    DownloadStatus,
    ResolvedSource,
    acquisition_input_digest,
    status_for_download_error,
)


def _src() -> ResolvedSource:
    return ResolvedSource(
        platform="tiktok",
        content_id="7298765432109876543",
        canonical_url="https://www.tiktok.com/@u/video/7298765432109876543",
        raw_input="https://vm.tiktok.com/x/",
    )


def test_input_digest_is_deterministic_and_format_sensitive() -> None:
    a = acquisition_input_digest(_src(), "best")
    b = acquisition_input_digest(_src(), "best")
    c = acquisition_input_digest(_src(), "bestvideo+bestaudio")
    assert a == b  # 逐位可重放
    assert a != c  # 格式选择变了摘要就变（作 Cache Key 一部分）
    assert len(a) == 64  # sha256 hex


def test_status_for_download_error() -> None:
    s = status_for_download_error
    C, S = AcquisitionErrorCode, DownloadStatus
    assert s(C.CHALLENGE_REQUIRED) is S.CHALLENGE
    assert s(C.AUTH_REQUIRED) is S.AUTH_REQUIRED
    assert s(C.UNCONFIGURED) is S.UNCONFIGURED
    assert s(C.RATE_LIMITED) is S.FAILED  # 其余归入 FAILED
    assert s(C.MEDIA_CORRUPT) is S.FAILED


def test_download_result_ok_property() -> None:
    ok = DownloadResult(status=DownloadStatus.OK, connector="download.yt_dlp")
    bad = DownloadResult(status=DownloadStatus.FAILED, connector="download.yt_dlp")
    assert ok.ok is True
    assert bad.ok is False


def test_manifest_carries_replay_provenance() -> None:
    m = AcquisitionManifest(
        source=_src(),
        provider="download.yt_dlp",
        tool="yt-dlp",
        tool_version="2025.01.15",
        format_selector="best",
        input_digest=acquisition_input_digest(_src(), "best"),
        output_sha256="a" * 64,
        output_size=1234,
        container="mp4",
        duration_s=12.3,
        resume_enabled=True,
        fetched_at=datetime.now(UTC),
    )
    assert m.tool_version == "2025.01.15"
    assert m.output_sha256 == "a" * 64
    assert m.input_digest == acquisition_input_digest(_src(), "best")
