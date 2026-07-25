"""VF-503 发布任务 domain 测试：§5 幂等键 + §4 状态机 + 重试不重复发布红线。"""

from datetime import UTC, datetime

import pytest

from videoforge_contracts import (
    PublishAttempt,
    PublishJob,
    PublishMethod,
    PublishPlatform,
    PublishState,
)
from videoforge_domain import (
    IllegalPublishTransition,
    PublishJobIssueKind,
    can_submit,
    compute_idempotency_key,
    confirm_success,
    has_submitted,
    new_publish_job,
    reconcile_publish,
    record_submission,
    to_waiting_for_human,
    validate_publish_job,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _key(**over) -> str:
    base = dict(
        account_id="a",
        platform=PublishPlatform.TIKTOK,
        render_digest="r",
        metadata_digest="m",
        scheduled_window="immediate",
    )
    base.update(over)
    return compute_idempotency_key(**base)


def _new() -> PublishJob:
    return new_publish_job(
        id="j1",
        account_id="a",
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.OFFICIAL_API,
        render_digest="r",
        metadata_digest="m",
        scheduled_window="immediate",
        created_at=_T0,
    )


def _uploading() -> PublishJob:
    return _new().model_copy(update={"state": PublishState.UPLOADING})


def _submitted() -> PublishJob:
    return record_submission(
        _uploading(), external_post_token="post_1", request_digest="rq1", now=_T0
    )


# --- §5 幂等键 ------------------------------------------------------------


def test_idempotency_key_deterministic():
    assert _key() == _key()


def test_idempotency_key_sensitive_to_each_input():
    base = _key()
    assert _key(account_id="b") != base
    assert _key(platform=PublishPlatform.DOUYIN) != base
    assert _key(render_digest="r2") != base
    assert _key(metadata_digest="m2") != base
    assert _key(scheduled_window="2026-08-01T00:00Z") != base


def test_new_job_is_pending_with_key():
    job = _new()
    assert job.state is PublishState.PENDING
    assert job.idempotency_key == _key()
    assert job.attempts == []


# --- §4 状态机 + 提交 -----------------------------------------------------


def test_submit_moves_to_submitted_and_records_attempt():
    job = _submitted()
    assert job.state is PublishState.SUBMITTED
    assert len(job.attempts) == 1
    assert job.attempts[0].external_post_token == "post_1"
    assert has_submitted(job) and not can_submit(job)


def test_double_submit_is_refused():
    # 核心红线（§13）：已提交的 Job 再提交必须被拒，绝不重复发布
    job = _submitted()
    with pytest.raises(IllegalPublishTransition, match="拒绝重复发布"):
        record_submission(job, external_post_token="post_2", request_digest="rq2", now=_T0)


def test_cannot_submit_from_pending():
    with pytest.raises(IllegalPublishTransition):
        record_submission(_new(), external_post_token="x", request_digest="r", now=_T0)


def test_has_submitted_true_for_post_submit_states():
    for st in (
        PublishState.SUBMITTED,
        PublishState.VERIFYING,
        PublishState.SUCCEEDED,
        PublishState.SUCCEEDED_RECONCILED,
    ):
        job = _new().model_copy(
            update={
                "state": st,
                "external_post_id": "e"
                if st in (PublishState.SUCCEEDED, PublishState.SUCCEEDED_RECONCILED)
                else None,
            }
        )
        assert has_submitted(job)
        assert not can_submit(job)


# --- §5 对账（不重发）----------------------------------------------------


def test_reconcile_found_marks_reconciled():
    job = _submitted()
    rec = reconcile_publish(
        job, found_external_post=True, external_id="ext_9", external_url="u", now=_T0
    )
    assert rec.state is PublishState.SUCCEEDED_RECONCILED
    assert rec.external_post_id == "ext_9"
    assert validate_publish_job(rec) == []


def test_reconcile_not_found_moves_to_verifying_no_resubmit():
    job = _submitted()
    ver = reconcile_publish(job, found_external_post=False, now=_T0)
    assert ver.state is PublishState.VERIFYING
    assert has_submitted(ver)  # 仍视为已提交，不会重发
    assert not can_submit(ver)


def test_reconcile_requires_external_id_when_found():
    with pytest.raises(ValueError, match="external_id"):
        reconcile_publish(_submitted(), found_external_post=True, now=_T0)


def test_reconcile_only_on_post_submit():
    with pytest.raises(IllegalPublishTransition):
        reconcile_publish(_uploading(), found_external_post=False, now=_T0)


def test_confirm_success_sets_external_id():
    job = _submitted().model_copy(update={"state": PublishState.VERIFYING})
    ok = confirm_success(job, external_id="ext_1", external_url="u", now=_T0)
    assert ok.state is PublishState.SUCCEEDED
    assert ok.external_post_id == "ext_1"


def test_to_waiting_for_human():
    job = _uploading()
    w = to_waiting_for_human(job, now=_T0)
    assert w.state is PublishState.WAITING_FOR_HUMAN


def test_terminal_states_have_no_outgoing():
    from videoforge_domain import PUBLISH_TRANSITIONS

    for st in (PublishState.SUCCEEDED, PublishState.SUCCEEDED_RECONCILED, PublishState.FAILED):
        assert PUBLISH_TRANSITIONS[st] == frozenset()


# --- 护栏 -----------------------------------------------------------------


def test_validate_flags_double_submit():
    job = _new().model_copy(
        update={
            "state": PublishState.SUBMITTED,
            "attempts": [
                PublishAttempt(attempt=1, request_digest="r1", external_post_token="p1", at=_T0),
                PublishAttempt(attempt=2, request_digest="r2", external_post_token="p2", at=_T0),
            ],
        }
    )
    kinds = {i.kind for i in validate_publish_job(job)}
    assert PublishJobIssueKind.DOUBLE_SUBMIT in kinds


def test_validate_flags_key_mismatch():
    job = _new().model_copy(update={"idempotency_key": "wrong"})
    kinds = {i.kind for i in validate_publish_job(job)}
    assert PublishJobIssueKind.IDEMPOTENCY_KEY_MISMATCH in kinds


def test_validate_flags_submitted_without_attempt():
    job = _new().model_copy(update={"state": PublishState.SUBMITTED, "attempts": []})
    kinds = {i.kind for i in validate_publish_job(job)}
    assert PublishJobIssueKind.SUBMITTED_WITHOUT_ATTEMPT in kinds


def test_clean_lifecycle_never_double_publishes():
    # 全流程：建 → 上传 → 提交 →（重试提交被拒）→ 对账成功；护栏全程干净、单一外部帖子
    job = _submitted()
    with pytest.raises(IllegalPublishTransition):
        record_submission(job, external_post_token="dup", request_digest="d", now=_T0)
    rec = reconcile_publish(job, found_external_post=True, external_id="ext", now=_T0)
    assert validate_publish_job(rec) == []
    posted = [a for a in rec.attempts if a.external_post_token]
    assert len(posted) == 1  # 只有一次真实提交
