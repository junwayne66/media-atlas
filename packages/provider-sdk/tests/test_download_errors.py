"""yt-dlp 失败签名 → §12 获取错误码。顺序即优先级：挑战最高，codec 早于 unavailable。"""

import pytest

from videoforge_provider_sdk.acquisition import AcquisitionErrorCode
from videoforge_provider_sdk.acquisition import AcquisitionErrorCode as C
from videoforge_provider_sdk.download_errors import map_ytdlp_error


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("ERROR: [tiktok] please complete the captcha to continue", C.CHALLENGE_REQUIRED),
        ("ERROR: 检测到异常，请完成安全验证", C.CHALLENGE_REQUIRED),
        ("ERROR: [youtube] Sign in to confirm your age", C.AUTH_REQUIRED),
        ("ERROR: This video is only available to members-only", C.AUTH_REQUIRED),
        ("ERROR: unable to download video data: HTTP Error 429: Too Many Requests", C.RATE_LIMITED),
        ("ERROR: Requested format is not available", C.UNSUPPORTED_CODEC),
        ("ERROR: [tiktok] 7123: Video unavailable", C.SOURCE_UNAVAILABLE),
        ("ERROR: This video is private", C.SOURCE_UNAVAILABLE),
        ("ERROR: [generic] Unable to extract webpage video data", C.CONNECTOR_SCHEMA_CHANGED),
        ("ERROR: Unsupported URL: https://example.com/x", C.CONNECTOR_SCHEMA_CHANGED),
        ("ERROR: The downloaded file is incomplete", C.DOWNLOAD_INCOMPLETE),
        ("ERROR: content too short (expected 1000 bytes)", C.DOWNLOAD_INCOMPLETE),
        ("ERROR: moov atom not found", C.MEDIA_CORRUPT),
        ("ERROR: something entirely new happened", C.RESULT_UNKNOWN),
    ],
)
def test_signature_maps_to_code(stderr: str, expected: AcquisitionErrorCode) -> None:
    assert map_ytdlp_error(stderr=stderr, returncode=1).code == expected


def test_codec_beats_unavailable_substring() -> None:
    # "not available" 是 unavailable 的子串，但格式不可用必须优先判为 UNSUPPORTED_CODEC
    err = map_ytdlp_error(stderr="ERROR: Requested format is not available. Use --list-formats")
    assert err.code == C.UNSUPPORTED_CODEC


def test_challenge_wins_over_other_markers() -> None:
    # 同时含 "429" 与 captcha 时，挑战（转人工）优先——绝不因限流重试而绕过风控
    err = map_ytdlp_error(stderr="HTTP Error 429 and captcha required")
    assert err.code == C.CHALLENGE_REQUIRED


def test_maps_from_exception_without_stderr() -> None:
    err = map_ytdlp_error(exc=RuntimeError("login required for this account"))
    assert err.code == C.AUTH_REQUIRED


def test_detail_is_last_stderr_line_not_full_stack() -> None:
    err = map_ytdlp_error(stderr="Traceback ...\nlots of lines\nERROR: This video is private")
    assert err.code == C.SOURCE_UNAVAILABLE
    assert "private" in err.detail.lower()
    assert "Traceback" not in err.detail
