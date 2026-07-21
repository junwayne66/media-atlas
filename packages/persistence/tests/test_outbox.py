import pytest
from sqlalchemy.exc import IntegrityError

from videoforge_persistence import OutboxRepository, record_event, try_claim_event


def test_producer_side_event_id_unique(session) -> None:
    """DoD：事件去重（生产端）。同 event_id 二次落库触发唯一约束。"""
    record_event(
        session,
        aggregate_type="project",
        aggregate_id="p1",
        event_type="t",
        payload={},
        event_id="e1",
    )
    session.flush()
    record_event(
        session,
        aggregate_type="project",
        aggregate_id="p1",
        event_type="t",
        payload={},
        event_id="e1",
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_consumer_side_dedupe_by_event_id(session) -> None:
    """DoD：事件去重（消费端）。首次认领 True，重复认领 False。"""
    assert try_claim_event(session, "e1", consumer="ranking") is True
    assert try_claim_event(session, "e1", consumer="ranking") is False
    # 不同消费者独立去重
    assert try_claim_event(session, "e1", consumer="analytics") is True


def test_pending_then_mark_published_idempotent(session) -> None:
    record_event(
        session,
        aggregate_type="project",
        aggregate_id="p1",
        event_type="a",
        payload={},
        event_id="e1",
    )
    record_event(
        session,
        aggregate_type="project",
        aggregate_id="p1",
        event_type="b",
        payload={},
        event_id="e2",
    )
    session.flush()
    repo = OutboxRepository(session)

    pending = repo.pending()
    assert [e.id for e in pending] == ["e1", "e2"]

    assert repo.mark_published("e1") is True
    assert repo.mark_published("e1") is False  # 幂等：重复确认不报错
    assert [e.id for e in repo.pending()] == ["e2"]
