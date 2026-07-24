"""P5 Exit 验收辅助：把 VF-501..507 的发布流程串成可跑的最小闭环（Fake-first）。

不触真实平台——用 Fake executor + domain 状态机跑：建 Job → 提交 → 校验 → 成功。
"""

from __future__ import annotations

from datetime import UTC, datetime

from videoforge_contracts import PublishMethod, PublishPlatform, PublishState
from videoforge_domain import (
    confirm_success,
    new_publish_job,
    record_submission,
)
from videoforge_provider_sdk import PublishExecStatus

T0 = datetime(2026, 7, 25, tzinfo=UTC)


def make_uploading_job(
    *, job_id: str = "j1", account_id: str = "acct_9",
    platform: PublishPlatform = PublishPlatform.TIKTOK,
    method: PublishMethod = PublishMethod.OFFICIAL_API,
    render: str = "r", metadata: str = "m", window: str = "immediate",
):
    """建一个已到 UPLOADING、待提交的 Job。"""
    j = new_publish_job(
        id=job_id, account_id=account_id, platform=platform, method=method,
        render_digest=render, metadata_digest=metadata, scheduled_window=window,
        created_at=T0,
    )
    return j.model_copy(update={"state": PublishState.UPLOADING})


def run_publish(executor, *, job=None, now=T0):
    """完整流程：submit → (OK 时) record_submission → query_status → confirm_success。

    返回 (最终 job, submit 结果)。非 OK（UNCONFIGURED/FAILED/CHALLENGE/AUTH_REQUIRED）
    时不提交，原样返回 job + 结果，供上层判定停/降级。
    """
    job = job or make_uploading_job()
    sub = executor.submit(job)
    if sub.status is not PublishExecStatus.OK:
        return job, sub
    job = record_submission(
        job, external_post_token=sub.external_post_token, request_digest="rq", now=now,
    )
    st = executor.query_status(job)
    job = confirm_success(
        job, external_id=sub.external_post_id,
        external_url=st.external_url if st.found_post else None, now=now,
    )
    return job, sub
