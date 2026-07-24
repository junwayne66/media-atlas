"""发布错误映射（docs/modules/44 §3.2 抖音 OpenAPI 错误映射）。

把平台返回的错误码/消息映射到结构化的 `PublishExecStatus` + `PublishExecErrorCode` +
是否需人工 / 是否可重试。**工具中立**：抖音 OpenAPI + 通用签名都走这里。

优先级（先严重/先安全）：授权 → 风控/挑战 → 限流 → 其它失败。授权失败与风控挑战都
`human_required=True`（转 WAITING_FOR_HUMAN，不盲目重试，§4.5/§13）；限流可重试。

**注**：真实抖音 OpenAPI 完整错误码表在接入真实平台（stop-condition）时补齐；此处提供
映射结构 + 关键词/代表码，Fake 与真实适配器共用同一套语义。
"""

from __future__ import annotations

from dataclasses import dataclass

from videoforge_provider_sdk.publish_executor import (
    PublishExecErrorCode,
    PublishExecStatus,
)

# 关键词（错误码或消息，小写匹配）。顺序内的匹配即命中该类。
_AUTH_KEYS: tuple[str, ...] = (
    "access_token", "accesstoken", "invalid_token", "token expired",
    "token 过期", "token无效", "unauthorized", "授权过期", "重新授权", "登录态",
    "auth expired", "scope", "permission denied", "2190008", "2190002",
)
_CHALLENGE_KEYS: tuple[str, ...] = (
    "风控", "验证码", "captcha", "risk", "challenge", "verify", "人机",
    "安全验证", "security check", "审核中", "manual review",
)
_RATE_KEYS: tuple[str, ...] = (
    "频率", "限流", "rate limit", "ratelimit", "rate_limit", "qps",
    "too many requests", "429", "触发限制",
)


@dataclass(frozen=True)
class PublishErrorMapping:
    status: PublishExecStatus
    error_code: PublishExecErrorCode
    human_required: bool  # 授权/风控 → 转人工，不盲目重试
    retryable: bool  # 限流等 → 退避后可重试


def _hit(haystack: str, keys: tuple[str, ...]) -> bool:
    return any(k in haystack for k in keys)


def map_publish_error(error_code: str, message: str = "") -> PublishErrorMapping:
    """把平台错误码/消息映射到结构化发布错误。工具中立、优先级从严。"""
    hay = f"{error_code} {message}".lower()

    if _hit(hay, _AUTH_KEYS):
        return PublishErrorMapping(
            PublishExecStatus.AUTH_REQUIRED, PublishExecErrorCode.AUTH_REQUIRED,
            human_required=True, retryable=False,
        )
    if _hit(hay, _CHALLENGE_KEYS):
        return PublishErrorMapping(
            PublishExecStatus.CHALLENGE, PublishExecErrorCode.CHALLENGE,
            human_required=True, retryable=False,
        )
    if _hit(hay, _RATE_KEYS):
        return PublishErrorMapping(
            PublishExecStatus.FAILED, PublishExecErrorCode.RATE_LIMITED,
            human_required=False, retryable=True,
        )
    return PublishErrorMapping(
        PublishExecStatus.FAILED, PublishExecErrorCode.UNKNOWN,
        human_required=False, retryable=False,
    )


__all__ = ["PublishErrorMapping", "map_publish_error"]
