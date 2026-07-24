"""P5 Exit —— 网络超时重试不重复发（§13 / §5）。

同一 PublishJob 反复重试**绝不重复发布**：提交后网络超时 → 先查状态/对账，匹配到已存在
外部帖子 → SUCCEEDED_RECONCILED，绝不盲目重发；盲目二次提交被硬拦。executor 层同样按
idempotency_key 幂等。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from p5_flow import make_uploading_job

from videoforge_contracts import PublishState
from videoforge_domain import (
    IllegalPublishTransition,
    PublishJobIssueKind,
    reconcile_publish,
    record_submission,
    to_waiting_for_human,
    validate_publish_job,
)
from videoforge_provider_sdk import FakeTikTokPublishExecutor

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _submitted():
    job = make_uploading_job()
    return record_submission(job, external_post_token="p1", request_digest="rq",
                              now=_T0)


def test_timeout_then_reconcile_no_resubmit():
    # 提交 → 网络超时（未知）→ 对账查到已存在帖子 → SUCCEEDED_RECONCILED，绝不重发
    job = _submitted()
    reconciled = reconcile_publish(job, found_external_post=True,
                                    external_id="ext_9", now=_T0)
    assert reconciled.state is PublishState.SUCCEEDED_RECONCILED
    assert reconciled.external_post_id == "ext_9"
    # 只有一次真实提交
    posted = [a for a in reconciled.attempts if a.external_post_token]
    assert len(posted) == 1
    assert validate_publish_job(reconciled) == []


def test_blind_resubmit_is_refused():
    job = _submitted()
    with pytest.raises(IllegalPublishTransition, match="拒绝重复发布"):
        record_submission(job, external_post_token="p2", request_digest="rq2",
                           now=_T0)


def test_resubmit_refused_even_after_human_recovery_loop():
    # 提交 → 等人工 → 恢复回 UPLOADING → 仍不能二次提交（token latch）
    job = _submitted()
    job = to_waiting_for_human(job, now=_T0)
    job = job.model_copy(update={"state": PublishState.UPLOADING})  # 人工恢复
    with pytest.raises(IllegalPublishTransition):
        record_submission(job, external_post_token="dup", request_digest="d", now=_T0)


def test_executor_idempotent_by_key():
    ex = FakeTikTokPublishExecutor()
    job = make_uploading_job()
    a = ex.submit(job)
    b = ex.submit(job)  # 同 idempotency_key 重试
    assert a.external_post_id == b.external_post_id  # 同一帖子
    assert b.idempotent_replay is True  # 未重复发布


def test_reconcile_not_found_keeps_querying_no_resubmit():
    job = _submitted()
    verifying = reconcile_publish(job, found_external_post=False, now=_T0)
    assert verifying.state is PublishState.VERIFYING  # 继续查，不重发
    # 仍视为已提交，不会再提交
    with pytest.raises(IllegalPublishTransition):
        record_submission(verifying.model_copy(update={"state": PublishState.UPLOADING}),
                           external_post_token="x", request_digest="x", now=_T0)


def test_no_job_ever_has_two_post_tokens():
    # 走完对账/成功后，护栏确保永不出现两个外部 post token（DOUBLE_SUBMIT）
    job = reconcile_publish(_submitted(), found_external_post=True,
                             external_id="e", now=_T0)
    assert PublishJobIssueKind.DOUBLE_SUBMIT not in {
        i.kind for i in validate_publish_job(job)}
