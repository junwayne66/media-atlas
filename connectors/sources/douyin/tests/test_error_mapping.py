"""外部错误 → 51 §12 统一错误码。"""

import pytest

from videoforge_connector_douyin import map_http_status, map_payload_error
from videoforge_provider_sdk import ConnectorErrorCode


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ConnectorErrorCode.AUTH_EXPIRED),
        (403, ConnectorErrorCode.AUTH_EXPIRED),
        (429, ConnectorErrorCode.RATE_LIMITED),
        (500, ConnectorErrorCode.PLATFORM_TEMPORARY),
        (503, ConnectorErrorCode.PLATFORM_TEMPORARY),
        (400, ConnectorErrorCode.PLATFORM_REJECTED),
        (418, ConnectorErrorCode.RESULT_UNKNOWN),
    ],
)
def test_http_status_mapping(status: int, expected: ConnectorErrorCode) -> None:
    assert map_http_status(status).code == expected


def test_captcha_payload_is_challenge() -> None:
    err = map_payload_error({"error_message": "请完成滑块验证"})
    assert err is not None
    assert err.code == ConnectorErrorCode.CHALLENGE_REQUIRED


def test_challenge_takes_precedence_over_http_status() -> None:
    # 即便 HTTP 200 面纱下，响应体含风控标记也判 CHALLENGE
    err = map_http_status(200, {"message": "captcha required"})
    assert err.code == ConnectorErrorCode.CHALLENGE_REQUIRED


def test_business_error_is_platform_rejected() -> None:
    err = map_payload_error({"error_code": 5001, "error_message": "invalid keyword"})
    assert err is not None
    assert err.code == ConnectorErrorCode.PLATFORM_REJECTED


def test_success_payload_has_no_error() -> None:
    assert map_payload_error({"error_code": 0, "items": []}) is None
    assert map_payload_error({"status_code": "success"}) is None


def test_marker_substring_in_data_is_not_challenge() -> None:
    # 业务数据里含 risk/slider 等子串不应误判为验证码（只扫错误/提示字段）
    data = {"items": [{"item_id": "sliderule-1", "hashtags": ["risk-management"]}]}
    assert map_payload_error(data) is None
