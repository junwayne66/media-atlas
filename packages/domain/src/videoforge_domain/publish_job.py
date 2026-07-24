"""发布任务幂等状态机（docs/modules/44 §4 PublishWorkflow + §5 幂等与未知状态）。纯函数。

- `compute_idempotency_key(...)`：§5 公式 sha256(account+platform+render+metadata+window)。
- `PUBLISH_TRANSITIONS` + `assert_transition`：§4 合法状态迁移。
- `record_submission`：**提交发帖——幂等硬拦**：已提交过（任一 attempt 带 external_post_token
  或状态已在 SUBMITTED 之后）绝不再提交，防重复发布（§5/§13）。
- `reconcile_publish`：§5 超时/未知后**先查状态**——匹配到已存在外部帖子 → `SUCCEEDED_RECONCILED`，
  否则转 VERIFYING 继续查，**绝不盲目重发**。
- `validate_publish_job`：幂等不变量护栏（重复提交、成功无外部 ID、key 不一致）。

**红线（§13）**：同一 PublishJob 反复重试**绝不重复发布**。真实平台发布是 stop-condition，
本层只做状态机 + 幂等，不触真实平台。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    PublishAttempt,
    PublishJob,
    PublishMethod,
    PublishPlatform,
    PublishState,
)

# §4 合法状态迁移。关键幂等不变量：SUBMITTED 之后**绝不**回到 UPLOADING/再次 SUBMITTED。
PUBLISH_TRANSITIONS: dict[PublishState, frozenset[PublishState]] = {
    PublishState.PENDING: frozenset({
        PublishState.PREFLIGHT_BLOCKED, PublishState.AWAITING_AUTH,
        PublishState.UPLOADING, PublishState.WAITING_FOR_HUMAN, PublishState.FAILED,
    }),
    PublishState.PREFLIGHT_BLOCKED: frozenset({
        PublishState.UPLOADING, PublishState.AWAITING_AUTH,
        PublishState.WAITING_FOR_HUMAN, PublishState.FAILED,
    }),
    PublishState.AWAITING_AUTH: frozenset({
        PublishState.UPLOADING, PublishState.WAITING_FOR_HUMAN, PublishState.FAILED,
    }),
    PublishState.UPLOADING: frozenset({
        PublishState.SUBMITTED, PublishState.AWAITING_AUTH,
        PublishState.WAITING_FOR_HUMAN, PublishState.FAILED,
    }),
    # 已提交后只能前进到校验/成功/对账/人工/失败——绝不回上传或再提交
    PublishState.SUBMITTED: frozenset({
        PublishState.VERIFYING, PublishState.SUCCEEDED,
        PublishState.SUCCEEDED_RECONCILED, PublishState.WAITING_FOR_HUMAN,
        PublishState.FAILED,
    }),
    PublishState.VERIFYING: frozenset({
        PublishState.SUCCEEDED, PublishState.SUCCEEDED_RECONCILED,
        PublishState.WAITING_FOR_HUMAN, PublishState.FAILED,
    }),
    # 人工恢复：前提交→UPLOADING / 后提交→VERIFYING；直连 SUBMITTED 由 can_submit 拦
    PublishState.WAITING_FOR_HUMAN: frozenset({
        PublishState.UPLOADING, PublishState.VERIFYING,
        PublishState.AWAITING_AUTH, PublishState.FAILED,
    }),
    PublishState.SUCCEEDED: frozenset(),
    PublishState.SUCCEEDED_RECONCILED: frozenset(),
    PublishState.FAILED: frozenset(),
}

_POST_SUBMIT_STATES = frozenset({
    PublishState.SUBMITTED, PublishState.VERIFYING,
    PublishState.SUCCEEDED, PublishState.SUCCEEDED_RECONCILED,
})


class IllegalPublishTransition(Exception):
    """非法状态迁移或违反幂等的提交尝试。"""


class PublishJobIssueKind(StrEnum):
    DOUBLE_SUBMIT = "DOUBLE_SUBMIT"  # 多个 attempt 带外部 post token（重复发布）
    SUCCEEDED_WITHOUT_EXTERNAL_ID = "SUCCEEDED_WITHOUT_EXTERNAL_ID"
    IDEMPOTENCY_KEY_MISMATCH = "IDEMPOTENCY_KEY_MISMATCH"
    SUBMITTED_WITHOUT_ATTEMPT = "SUBMITTED_WITHOUT_ATTEMPT"


@dataclass(frozen=True)
class PublishJobIssue:
    kind: PublishJobIssueKind
    ref: str
    detail: str


def compute_idempotency_key(
    *,
    account_id: str,
    platform: PublishPlatform,
    render_digest: str,
    metadata_digest: str,
    scheduled_window: str,
) -> str:
    """§5 幂等键：同 (账号 + 平台 + 成片 + 元数据 + 计划窗口) 永远同键。"""
    payload = {
        "account_id": account_id,
        "platform": platform.value,
        "render_digest": render_digest,
        "metadata_digest": metadata_digest,
        "scheduled_window": scheduled_window,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def can_transition(a: PublishState, b: PublishState) -> bool:
    return b in PUBLISH_TRANSITIONS.get(a, frozenset())


def assert_transition(a: PublishState, b: PublishState) -> None:
    if not can_transition(a, b):
        raise IllegalPublishTransition(f"非法发布状态迁移：{a.value} → {b.value}")


def has_submitted(job: PublishJob) -> bool:
    """是否已经提交过发帖（durable：看 attempts 的外部 token + 状态）。"""
    if job.state in _POST_SUBMIT_STATES:
        return True
    return any(a.external_post_token for a in job.attempts)


def can_submit(job: PublishJob) -> bool:
    """只有在 UPLOADING 且**从未提交过**时才允许提交（幂等硬拦）。"""
    return job.state is PublishState.UPLOADING and not has_submitted(job)


def new_publish_job(
    *,
    id: str,
    account_id: str,
    platform: PublishPlatform,
    method: PublishMethod,
    render_digest: str,
    metadata_digest: str,
    scheduled_window: str,
    created_at: datetime,
) -> PublishJob:
    """建一个 PENDING 发布任务，幂等键按 §5 计算。"""
    key = compute_idempotency_key(
        account_id=account_id, platform=platform, render_digest=render_digest,
        metadata_digest=metadata_digest, scheduled_window=scheduled_window,
    )
    return PublishJob(
        id=id, idempotency_key=key, account_id=account_id, platform=platform,
        method=method, render_digest=render_digest, metadata_digest=metadata_digest,
        scheduled_window=scheduled_window, state=PublishState.PENDING,
        attempts=[], created_at=created_at, updated_at=created_at,
    )


def record_submission(
    job: PublishJob, *, external_post_token: str, request_digest: str,
    now: datetime, external_upload_token: str | None = None,
) -> PublishJob:
    """提交发帖 → SUBMITTED。**幂等硬拦**：已提交过就抛异常，绝不重复发布。"""
    if not can_submit(job):
        raise IllegalPublishTransition(
            f"job {job.id!r} 已提交过或状态 {job.state.value} 不允许提交"
            "——拒绝重复发布（§5/§13 幂等）"
        )
    assert_transition(job.state, PublishState.SUBMITTED)
    attempt = PublishAttempt(
        attempt=len(job.attempts) + 1, request_digest=request_digest,
        external_upload_token=external_upload_token,
        external_post_token=external_post_token, at=now,
    )
    return job.model_copy(update={
        "state": PublishState.SUBMITTED,
        "attempts": [*job.attempts, attempt],
        "updated_at": now,
    })


def reconcile_publish(
    job: PublishJob, *, found_external_post: bool, now: datetime,
    external_id: str | None = None, external_url: str | None = None,
) -> PublishJob:
    """§5 超时/未知后对账：查到已存在外部帖子 → SUCCEEDED_RECONCILED；否则转 VERIFYING
    继续查，**绝不盲目重发**。只对已提交（post-submit）的 Job 有意义。"""
    if job.state not in (
        PublishState.SUBMITTED, PublishState.VERIFYING,
        PublishState.WAITING_FOR_HUMAN,
    ):
        raise IllegalPublishTransition(
            f"reconcile 只用于已提交的 Job，当前 {job.state.value}"
        )
    if found_external_post:
        if not external_id:
            raise ValueError("found_external_post=True 时必须提供 external_id")
        assert_transition(job.state, PublishState.SUCCEEDED_RECONCILED)
        return job.model_copy(update={
            "state": PublishState.SUCCEEDED_RECONCILED,
            "external_post_id": external_id, "external_url": external_url,
            "updated_at": now,
        })
    # 未查到 → 继续校验（不回退、不重发）
    target = (
        PublishState.VERIFYING if can_transition(job.state, PublishState.VERIFYING)
        else job.state
    )
    return job.model_copy(update={"state": target, "updated_at": now})


def confirm_success(
    job: PublishJob, *, external_id: str, now: datetime,
    external_url: str | None = None, content_fingerprint: str | None = None,
) -> PublishJob:
    """确认发布成功（§4.10 保存外部 ID/URL/指纹）→ SUCCEEDED。"""
    assert_transition(job.state, PublishState.SUCCEEDED)
    return job.model_copy(update={
        "state": PublishState.SUCCEEDED, "external_post_id": external_id,
        "external_url": external_url, "content_fingerprint": content_fingerprint,
        "updated_at": now,
    })


def to_waiting_for_human(job: PublishJob, *, now: datetime) -> PublishJob:
    """挑战/授权失败 → WAITING_FOR_HUMAN（§4.5/§13，不盲目继续）。"""
    assert_transition(job.state, PublishState.WAITING_FOR_HUMAN)
    return job.model_copy(update={
        "state": PublishState.WAITING_FOR_HUMAN, "updated_at": now,
    })


def validate_publish_job(job: PublishJob) -> list[PublishJobIssue]:
    """幂等不变量护栏。"""
    issues: list[PublishJobIssue] = []
    posted = [a for a in job.attempts if a.external_post_token]
    if len(posted) > 1:
        tokens = {a.external_post_token for a in posted}
        issues.append(PublishJobIssue(
            PublishJobIssueKind.DOUBLE_SUBMIT, job.id,
            f"{len(posted)} 次带外部 post token 的提交（tokens={tokens}）——重复发布风险",
        ))
    if (
        job.state in (PublishState.SUCCEEDED, PublishState.SUCCEEDED_RECONCILED)
        and not job.external_post_id
    ):
        issues.append(PublishJobIssue(
            PublishJobIssueKind.SUCCEEDED_WITHOUT_EXTERNAL_ID, job.id,
            "成功态却无 external_post_id",
        ))
    expected = compute_idempotency_key(
        account_id=job.account_id, platform=job.platform,
        render_digest=job.render_digest, metadata_digest=job.metadata_digest,
        scheduled_window=job.scheduled_window,
    )
    if expected != job.idempotency_key:
        issues.append(PublishJobIssue(
            PublishJobIssueKind.IDEMPOTENCY_KEY_MISMATCH, job.id,
            "idempotency_key 与按 Job 字段重算的不一致",
        ))
    if job.state is PublishState.SUBMITTED and not job.attempts:
        issues.append(PublishJobIssue(
            PublishJobIssueKind.SUBMITTED_WITHOUT_ATTEMPT, job.id,
            "SUBMITTED 却无任何 attempt 记录",
        ))
    return issues


def is_valid_publish_job(job: PublishJob) -> bool:
    return not validate_publish_job(job)
