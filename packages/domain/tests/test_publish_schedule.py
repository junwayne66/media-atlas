"""VF-507 日程 + 副本键 + 手工完成 domain 测试（§4.4 + §5）。"""

from datetime import UTC, datetime, time

import pytest

from videoforge_contracts import PublishMethod, PublishPlatform, PublishState
from videoforge_domain import (
    IllegalPublishTransition,
    PublishJobIssueKind,
    compute_copy_idempotency_key,
    compute_idempotency_key,
    is_within_publishing_window,
    mark_manually_completed,
    new_publish_job,
    next_publish_time,
    parse_publishing_window,
    reconcile_publish,
    record_submission,
    to_waiting_for_human,
    validate_publish_job,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _at(h: int, m: int = 0) -> datetime:
    return datetime(2026, 7, 25, h, m, tzinfo=UTC)


# --- §4.4 日程 -----------------------------------------------------------


def test_parse_window():
    assert parse_publishing_window("18:00-22:00") == (time(18, 0), time(22, 0))
    assert parse_publishing_window("immediate") is None
    assert parse_publishing_window("") is None


def test_parse_window_invalid():
    with pytest.raises(ValueError):
        parse_publishing_window("18:00")  # 无 '-'
    with pytest.raises(ValueError):
        parse_publishing_window("25:00-26:00")  # 非法时刻


def test_within_window_same_day():
    assert is_within_publishing_window("18:00-22:00", _at(19))
    assert not is_within_publishing_window("18:00-22:00", _at(12))
    assert not is_within_publishing_window("18:00-22:00", _at(23))


def test_within_window_wraparound():
    # 22:00-02:00 跨零点
    assert is_within_publishing_window("22:00-02:00", _at(23))
    assert is_within_publishing_window("22:00-02:00", _at(1))
    assert not is_within_publishing_window("22:00-02:00", _at(12))


def test_immediate_always_within():
    assert is_within_publishing_window("immediate", _at(3))


def test_next_publish_time():
    # 窗口前 → 今天开窗
    assert next_publish_time("18:00-22:00", _at(12)) == _at(18)
    # 窗口后 → 明天开窗
    assert next_publish_time("18:00-22:00", _at(23)) == datetime(2026, 7, 26, 18, 0, tzinfo=UTC)
    # 窗口内 → 立即（原时刻）
    assert next_publish_time("18:00-22:00", _at(19)) == _at(19)
    # immediate → 立即
    assert next_publish_time("immediate", _at(12)) == _at(12)


# --- §5 副本键（重复帖子防护）-------------------------------------------


def _key(copy_index: int) -> str:
    return compute_copy_idempotency_key(
        account_id="a",
        platform=PublishPlatform.TIKTOK,
        render_digest="r",
        metadata_digest="m",
        scheduled_window="immediate",
        copy_index=copy_index,
    )


def test_copy_zero_equals_base_for_dedup():
    base = compute_idempotency_key(
        account_id="a",
        platform=PublishPlatform.TIKTOK,
        render_digest="r",
        metadata_digest="m",
        scheduled_window="immediate",
    )
    assert _key(0) == base  # 同内容 → 同键 → 去重，不重复发布


def test_copies_get_distinct_keys():
    assert _key(1) != _key(0)
    assert _key(2) != _key(1)
    assert len({_key(i) for i in range(5)}) == 5  # 每个副本键都不同


def test_negative_copy_index_rejected():
    with pytest.raises(ValueError):
        _key(-1)


# --- §5 手工完成 + reconcile-from-human 修复 ----------------------------


def _human_waiting():
    j = new_publish_job(
        id="j",
        account_id="a",
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.ANDROID_DEVICE,
        render_digest="r",
        metadata_digest="m",
        scheduled_window="immediate",
        created_at=_T0,
    ).model_copy(update={"state": PublishState.UPLOADING})
    j = record_submission(j, external_post_token="p1", request_digest="rq", now=_T0)
    return to_waiting_for_human(j, now=_T0)


def test_manual_completion():
    mc = mark_manually_completed(_human_waiting(), external_id="ext_manual", now=_T0)
    assert mc.state is PublishState.SUCCEEDED_RECONCILED
    assert mc.external_post_id == "ext_manual"
    assert validate_publish_job(mc) == []


def test_manual_completion_requires_external_id():
    with pytest.raises(ValueError):
        mark_manually_completed(_human_waiting(), external_id="", now=_T0)


def test_manual_completion_only_from_waiting_for_human():
    j = new_publish_job(
        id="j",
        account_id="a",
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.OFFICIAL_API,
        render_digest="r",
        metadata_digest="m",
        scheduled_window="immediate",
        created_at=_T0,
    ).model_copy(update={"state": PublishState.UPLOADING})
    with pytest.raises(IllegalPublishTransition):
        mark_manually_completed(j, external_id="x", now=_T0)


def test_manual_completion_never_double_publishes():
    mc = mark_manually_completed(_human_waiting(), external_id="ext", now=_T0)
    # 只有一次真实提交记录，手工完成不新增提交
    posted = [a for a in mc.attempts if a.external_post_token]
    assert len(posted) == 1
    assert PublishJobIssueKind.DOUBLE_SUBMIT not in {i.kind for i in validate_publish_job(mc)}


def test_reconcile_from_waiting_for_human_now_works():
    # VF-503 潜在不一致：reconcile 接受 WAITING_FOR_HUMAN 却被迁移表拒 → 现已修
    rec = reconcile_publish(
        _human_waiting(), found_external_post=True, external_id="ext_rec", now=_T0
    )
    assert rec.state is PublishState.SUCCEEDED_RECONCILED
    assert rec.external_post_id == "ext_rec"
