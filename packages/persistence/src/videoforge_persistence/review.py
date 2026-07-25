"""审核决定仓储（VF-501 ReviewDecision）。

只说合同对象；列是过滤投影（entity_id / entity_version / scope / decision），真值在 payload。
**只增不改**——一次审批是一条不可变事实；"修改失效"由 domain 的 `is_approval_valid`
按当前 version + content_digest 重判，而不是回头改写旧记录。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from videoforge_contracts import ReviewDecision
from videoforge_persistence.creation_tables import ReviewDecisionRow
from videoforge_persistence.errors import DuplicateError, NotFoundError


def _to_row(decision: ReviewDecision) -> ReviewDecisionRow:
    return ReviewDecisionRow(
        id=decision.id,
        entity_id=decision.entity_id,
        entity_version=decision.entity_version,
        scope=str(decision.scope),
        decision=str(decision.decision),
        payload=decision.model_dump(mode="json"),
        created_at=decision.created_at,
    )


def _from_row(row: ReviewDecisionRow) -> ReviewDecision:
    return ReviewDecision.model_validate(row.payload)


class ReviewDecisionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, decision: ReviewDecision) -> ReviewDecision:
        self._session.add(_to_row(decision))
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(f"review_decision 已存在: {decision.id}") from exc
        return decision

    def get(self, decision_id: str) -> ReviewDecision:
        row = self._session.get(ReviewDecisionRow, decision_id)
        if row is None:
            raise NotFoundError("review_decision", decision_id)
        return _from_row(row)

    def list_for_entity(self, entity_id: str, *, limit: int = 50) -> list[ReviewDecision]:
        stmt = (
            select(ReviewDecisionRow)
            .where(ReviewDecisionRow.entity_id == entity_id)
            .order_by(ReviewDecisionRow.created_at.desc(), ReviewDecisionRow.id)
            .limit(limit)
        )
        return [_from_row(r) for r in self._session.scalars(stmt)]


__all__ = ["ReviewDecisionRepository"]
