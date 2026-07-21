from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from videoforge_persistence.ids import new_id
from videoforge_persistence.tables import OutboxEventRow, ProcessedEventRow


@dataclass(frozen=True)
class OutboxEvent:
    """pending() 的返回载体：纯数据，会话关闭后仍可安全使用。"""

    id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    attempts: int


def record_event(
    session: Session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> str:
    """在**当前事务**内追加一条 outbox 事件；与领域写一起提交或一起回滚。"""
    eid = event_id or new_id()
    session.add(
        OutboxEventRow(
            id=eid,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
    )
    return eid


def try_claim_event(session: Session, event_id: str, consumer: str) -> bool:
    """消费端按 event_id 去重（docs/architecture/31 §7）。

    首次认领返回 True；重复事件返回 False，调用方应直接跳过处理。
    认领与业务处理放在同一事务中即可获得恰好一次的效果。
    """
    stmt = (
        pg_insert(ProcessedEventRow)
        .values(event_id=event_id, consumer=consumer, processed_at=datetime.now(UTC))
        .on_conflict_do_nothing(index_elements=["event_id", "consumer"])
        # RETURNING 只在真插入时返回行；INSERT 的 rowcount 在部分驱动下为 -1，不可依赖
        .returning(ProcessedEventRow.event_id)
    )
    return session.execute(stmt).scalar_one_or_none() is not None


class OutboxRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def pending(self, limit: int = 100) -> list[OutboxEvent]:
        stmt = (
            select(OutboxEventRow)
            .where(OutboxEventRow.published_at.is_(None))
            .order_by(OutboxEventRow.occurred_at)
            .limit(limit)
        )
        return [
            OutboxEvent(
                id=r.id,
                aggregate_type=r.aggregate_type,
                aggregate_id=r.aggregate_id,
                event_type=r.event_type,
                payload=r.payload,
                occurred_at=r.occurred_at,
                attempts=r.attempts,
            )
            for r in self._session.scalars(stmt)
        ]

    def mark_published(self, event_id: str) -> bool:
        """发布确认；幂等——已发布的事件重复确认返回 False，不报错。"""
        stmt = (
            update(OutboxEventRow)
            .where(OutboxEventRow.id == event_id, OutboxEventRow.published_at.is_(None))
            .values(published_at=datetime.now(UTC), attempts=OutboxEventRow.attempts + 1)
        )
        return self._session.execute(stmt).rowcount == 1
