"""yt-dlp/下载失败签名 → 获取层 §12 错误码（docs/modules/41 §12）。纯函数，无副作用。

错误类别决定重试/切 Provider/人工/终止，禁止只返回字符串堆栈。原始脱敏 stderr 由
调用方另存诊断 Artifact。工具无关：任何下载后端的失败文本都可套本映射。

匹配顺序即优先级——挑战/风控优先转人工（绝不绕过），且「格式不可用（codec）」
必须早于泛化的「不可用（unavailable）」，否则 "requested format is not available"
会被 "not available" 误判为 SOURCE_UNAVAILABLE。
"""

from __future__ import annotations

from videoforge_provider_sdk.acquisition import AcquisitionErrorCode


class AcquisitionError(Exception):
    def __init__(self, code: AcquisitionErrorCode, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else str(code))
        self.code = code
        self.detail = detail


# 验证码/风控（转人工，不绕过）——最高优先级
_CHALLENGE = (
    "captcha",
    "robot check",
    "verify you're human",
    "verify you are human",
    "unusual traffic",
    "security check",
    "滑块",
    "验证码",
    "人机验证",
    "安全验证",
)
# 需登录凭据（Cookie handle）：转人工提供凭据，不绕过
_AUTH = (
    "sign in",
    "log in",
    "login required",
    "login is required",
    "requires authentication",
    "authentication",
    "confirm your age",
    "age-restricted",
    "age restricted",
    "members-only",
    "member-only",
    "use --cookies",
    "cookies are required",
    "account cookies",
)
_RATE = (
    "429",
    "too many requests",
    "rate-limit",
    "rate limit",
    "temporarily blocked",
    "try again later",
)
# 格式/编码不可用——必须早于 unavailable（含 "not available" 子串）
_CODEC = (
    "requested format is not available",
    "requested format not available",
    "no such format",
    "unsupported codec",
    "no video formats found",
    "no formats found",
)
_UNAVAILABLE = (
    "video unavailable",
    "video is unavailable",
    "no longer available",
    "has been removed",
    "this video is private",
    "private video",
    "account is private",
    "content isn't available",
    "video not found",  # 收窄：避免撞 "moov atom not found"（损坏签名）
    "http error 404",
    "http error 410",
    "has been deleted",
    "does not exist",
    "removed by the user",
)
# 提取器/连接器假设失效（页面结构变化）——L4 熔断信号
_SCHEMA = (
    "unable to extract",
    "unsupported url",
    "unable to download webpage",
    "failed to parse json",
    "unable to parse",
    "extractorerror",
    "unable to find",
)
_INCOMPLETE = (
    "download interrupted",
    "incomplete",
    "partial file",
    "content too short",
    "connection reset",
    "the read operation timed out",
    "chunk too big",
)
_CORRUPT = (
    "moov atom not found",
    "invalid data found",
    "corrupt",
    "malformed",
)

# (错误码, 标记) 有序表——返回首个命中
_RULES: tuple[tuple[AcquisitionErrorCode, tuple[str, ...]], ...] = (
    (AcquisitionErrorCode.CHALLENGE_REQUIRED, _CHALLENGE),
    (AcquisitionErrorCode.AUTH_REQUIRED, _AUTH),
    (AcquisitionErrorCode.RATE_LIMITED, _RATE),
    (AcquisitionErrorCode.UNSUPPORTED_CODEC, _CODEC),
    (AcquisitionErrorCode.SOURCE_UNAVAILABLE, _UNAVAILABLE),
    (AcquisitionErrorCode.CONNECTOR_SCHEMA_CHANGED, _SCHEMA),
    (AcquisitionErrorCode.DOWNLOAD_INCOMPLETE, _INCOMPLETE),
    (AcquisitionErrorCode.MEDIA_CORRUPT, _CORRUPT),
)


def map_ytdlp_error(
    *,
    returncode: int | None = None,
    stderr: str = "",
    exc: BaseException | None = None,
) -> AcquisitionError:
    """下载失败签名 → AcquisitionError。stderr/异常文本都参与匹配。"""
    text = (stderr or "").lower()
    if exc is not None:
        text = f"{text} {exc}".lower()
    for code, markers in _RULES:
        if any(marker in text for marker in markers):
            detail = stderr.strip().splitlines()[-1][:300] if stderr.strip() else str(exc or code)
            return AcquisitionError(code, detail)
    detail = stderr.strip().splitlines()[-1][:300] if stderr.strip() else f"returncode={returncode}"
    return AcquisitionError(AcquisitionErrorCode.RESULT_UNKNOWN, detail)
