"""发布执行端口 + Fake（docs/modules/44 §3.1 TikTok 生命周期 + §5 幂等）。

`creator_info()` / `submit(job)` / `query_status(job)` 抽象 TikTok Content Posting API 的
关键动作。**真实实现（Direct Post、Creator Info、上传、Webhook）需真实平台账号 + 官方 API +
应用审核 + 凭据 → stop-condition**：`UnconfiguredTikTokPublishExecutor` 恒返 UNCONFIGURED，
**零 live network**（grep/AST 可验）。

`FakeTikTokPublishExecutor` 确定性模拟，无网络；**按 idempotency_key 幂等**——同一 Job 重复
submit 返回**同一** external_post_id（不产生第二个帖子），端到端印证 §5/§13"重试不重复发布"。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import PublishJob


class PublishExecStatus(StrEnum):
    OK = "OK"
    UNCONFIGURED = "UNCONFIGURED"
    FAILED = "FAILED"
    CHALLENGE = "CHALLENGE"  # 风控/验证码 → 上层转 WAITING_FOR_HUMAN
    AUTH_REQUIRED = "AUTH_REQUIRED"  # 需授权/刷新 Token → 上层转 WAITING_FOR_HUMAN


class PublishExecErrorCode(StrEnum):
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CHALLENGE = "CHALLENGE"
    RATE_LIMITED = "RATE_LIMITED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CreatorInfoResult:
    status: PublishExecStatus
    can_post: bool = False
    privacy_options: tuple[str, ...] = ()
    error_code: PublishExecErrorCode | None = None
    detail: str | None = None


@dataclass(frozen=True)
class SubmitResult:
    status: PublishExecStatus
    external_post_id: str | None = None
    external_post_token: str | None = None
    idempotent_replay: bool = False  # True = 命中已提交，返回已存在帖子（未重复发布）
    error_code: PublishExecErrorCode | None = None
    detail: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StatusResult:
    status: PublishExecStatus
    found_post: bool = False
    external_post_id: str | None = None
    external_url: str | None = None
    error_code: PublishExecErrorCode | None = None
    detail: str | None = None


@runtime_checkable
class PublishExecutor(Protocol):
    """§3.1 发布执行端口。真实平台调用延后（VF-503 stop-condition）。"""

    name: str

    def creator_info(self) -> CreatorInfoResult: ...

    def submit(self, job: PublishJob) -> SubmitResult: ...

    def query_status(self, job: PublishJob) -> StatusResult: ...


class UnconfiguredTikTokPublishExecutor:
    """诚实占位：无真实平台账号/凭据/应用审核 → 恒 UNCONFIGURED，绝不发布，零 live network。"""

    def __init__(self, *, name: str = "publish.tiktok.unconfigured") -> None:
        self.name = name

    def creator_info(self) -> CreatorInfoResult:
        return CreatorInfoResult(
            status=PublishExecStatus.UNCONFIGURED,
            error_code=PublishExecErrorCode.ENGINE_UNAVAILABLE,
            detail="未配置真实 TikTok 官方 API（需账号 + 应用审核 + 凭据，stop-condition）",
        )

    def submit(self, job: PublishJob) -> SubmitResult:
        return SubmitResult(
            status=PublishExecStatus.UNCONFIGURED,
            error_code=PublishExecErrorCode.ENGINE_UNAVAILABLE,
            detail="未配置真实 TikTok 发布，绝不触真实平台",
        )

    def query_status(self, job: PublishJob) -> StatusResult:
        return StatusResult(
            status=PublishExecStatus.UNCONFIGURED,
            error_code=PublishExecErrorCode.ENGINE_UNAVAILABLE,
        )


class FakeTikTokPublishExecutor:
    """确定性 Fake：零网络，按 idempotency_key 幂等。

    - `challenge`/`auth_required` 可注入 → submit 返回 CHALLENGE/AUTH_REQUIRED（上层转人工）。
    - 否则首次 submit 生成确定性 external_post_id 并按 idempotency_key 记住；**同 key 再 submit
      返回同一 id 且 `idempotent_replay=True`**（不产生第二个帖子）。
    - `preexisting`：模拟"提交前平台已有匹配帖子"（用于对账 SUCCEEDED_RECONCILED）。
    """

    def __init__(self, *, name: str = "publish.tiktok.fake",
                  challenge: bool = False, auth_required: bool = False,
                  preexisting: bool = False) -> None:
        self.name = name
        self.challenge = challenge
        self.auth_required = auth_required
        self.preexisting = preexisting
        self._posted: dict[str, str] = {}  # idempotency_key -> external_post_id

    def creator_info(self) -> CreatorInfoResult:
        if self.auth_required:
            return CreatorInfoResult(
                status=PublishExecStatus.AUTH_REQUIRED,
                error_code=PublishExecErrorCode.AUTH_REQUIRED,
                detail="Fake：需授权",
            )
        return CreatorInfoResult(
            status=PublishExecStatus.OK, can_post=True,
            privacy_options=("PUBLIC", "FOLLOWERS", "PRIVATE"),
        )

    def submit(self, job: PublishJob) -> SubmitResult:
        if self.auth_required:
            return SubmitResult(
                status=PublishExecStatus.AUTH_REQUIRED,
                error_code=PublishExecErrorCode.AUTH_REQUIRED, detail="Fake：需授权")
        if self.challenge:
            return SubmitResult(
                status=PublishExecStatus.CHALLENGE,
                error_code=PublishExecErrorCode.CHALLENGE, detail="Fake：风控挑战")
        key = job.idempotency_key
        if key in self._posted:  # 幂等：已提交过 → 返回同一帖子，不重复发布
            return SubmitResult(
                status=PublishExecStatus.OK,
                external_post_id=self._posted[key],
                external_post_token=f"tok-{key[:12]}",
                idempotent_replay=True,
                warnings=["幂等命中：同 idempotency_key 已提交，返回已存在帖子"],
            )
        external_post_id = f"fake-post-{key[:16]}"
        self._posted[key] = external_post_id
        return SubmitResult(
            status=PublishExecStatus.OK, external_post_id=external_post_id,
            external_post_token=f"tok-{key[:12]}",
            warnings=["Fake TikTok：非真实发布"],
        )

    def query_status(self, job: PublishJob) -> StatusResult:
        key = job.idempotency_key
        if self.preexisting or key in self._posted:
            post_id = self._posted.get(key, f"fake-post-{key[:16]}")
            return StatusResult(
                status=PublishExecStatus.OK, found_post=True,
                external_post_id=post_id,
                external_url=f"https://www.tiktok.com/@fake/video/{post_id}",
            )
        return StatusResult(status=PublishExecStatus.OK, found_post=False)


__all__ = [
    "CreatorInfoResult",
    "FakeTikTokPublishExecutor",
    "PublishExecErrorCode",
    "PublishExecStatus",
    "PublishExecutor",
    "StatusResult",
    "SubmitResult",
    "UnconfiguredTikTokPublishExecutor",
]
