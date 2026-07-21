"""外部错误 → 统一连接器错误码（docs/implementation/51 §12）。

纯函数，无副作用；原始脱敏响应由调用方另存为诊断 Artifact（51 §12）。
"""

from typing import Any

from videoforge_provider_sdk import ConnectorErrorCode


class ConnectorError(Exception):
    def __init__(self, code: ConnectorErrorCode, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else str(code))
        self.code = code
        self.detail = detail


def map_http_status(status_code: int, payload: dict[str, Any] | None = None) -> ConnectorError:
    """HTTP 状态码 + 可选响应体 → ConnectorError。"""
    if payload is not None:
        payload_err = map_payload_error(payload)
        if payload_err is not None:
            return payload_err
    if status_code in (401, 403):
        return ConnectorError(ConnectorErrorCode.AUTH_EXPIRED, f"HTTP {status_code}")
    if status_code == 429:
        return ConnectorError(ConnectorErrorCode.RATE_LIMITED, "HTTP 429")
    if status_code in (500, 502, 503, 504):
        return ConnectorError(ConnectorErrorCode.PLATFORM_TEMPORARY, f"HTTP {status_code}")
    if status_code == 400:
        return ConnectorError(ConnectorErrorCode.PLATFORM_REJECTED, "HTTP 400")
    return ConnectorError(ConnectorErrorCode.RESULT_UNKNOWN, f"HTTP {status_code}")


# 验证码/风控标记（转人工，不绕过）。只在错误/提示字段与顶层键名里找，
# 不扫业务数据——否则含 "risk"/"slider" 等子串的合法 hashtag/item_id 会误判。
_CHALLENGE_MARKERS = ("captcha", "verify", "risk", "slider", "验证码", "滑块", "安全验证")
_MESSAGE_FIELDS = ("error_message", "message", "prompt", "description", "hint", "reason", "detail")


def map_payload_error(payload: dict[str, Any]) -> ConnectorError | None:
    """从平台响应体识别错误；无错误返回 None。"""
    # 挑战检测的搜索域：顶层键名 + 提示类字段的值（不含 items 等业务数据）
    parts = list(payload.keys())
    parts.extend(str(payload[f]) for f in _MESSAGE_FIELDS if isinstance(payload.get(f), str))
    haystack = " ".join(parts).lower()
    if any(marker in haystack for marker in _CHALLENGE_MARKERS):
        return ConnectorError(ConnectorErrorCode.CHALLENGE_REQUIRED, "平台要求人机验证")
    # 平台业务错误码（中性字段名，非抖音私有结构）
    code = payload.get("error_code") or payload.get("status_code")
    if code in (None, 0, "0", "success"):
        return None
    message = str(payload.get("error_message") or payload.get("message") or code)
    return ConnectorError(ConnectorErrorCode.PLATFORM_REJECTED, message)
