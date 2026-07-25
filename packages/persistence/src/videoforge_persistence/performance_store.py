"""表现快照仓储（VF-601 PerformanceSnapshot）。

快照是**不可变观测事实**：`create_if_absent` 对同 (post_id, age_hours) **幂等返回既有**
（不覆盖、不写第二条）——重复采集不该改写已发生的观测。

**null 语义（§10 红线）**：payload 整存整取，缺失指标在库里就是 JSON null，读回仍是 None，
绝不在持久化层补 0。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from videoforge_contracts import PerformanceSnapshot, PublishPlatform
from videoforge_persistence.creation_tables import PerformanceSnapshotRow
from videoforge_persistence.errors import NotFoundError


def _from_row(row: PerformanceSnapshotRow) -> PerformanceSnapshot:
    return PerformanceSnapshot.model_validate(row.payload)


class PerformanceSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_if_absent(self, snapshot: PerformanceSnapshot) -> tuple[PerformanceSnapshot, bool]:
        """返回 (快照, 是否新建)。同 (post_id, age_hours) 已存在 → 幂等返回既有。"""
        existing = self.find(snapshot.platform_post_id, snapshot.age_hours)
        if existing is not None:
            return existing, False
        row = PerformanceSnapshotRow(
            id=snapshot.id,
            account_id=snapshot.account_id,
            platform=str(snapshot.platform),
            post_id=snapshot.platform_post_id,
            age_hours=snapshot.age_hours,
            payload=snapshot.model_dump(mode="json"),
            observed_at=snapshot.observed_at,
            created_at=snapshot.observed_at,
        )
        self._session.add(row)
        self._session.flush()
        return snapshot, True

    def find(self, post_id: str, age_hours: float) -> PerformanceSnapshot | None:
        stmt = select(PerformanceSnapshotRow).where(
            PerformanceSnapshotRow.post_id == post_id,
            PerformanceSnapshotRow.age_hours == age_hours,
        )
        row = self._session.scalars(stmt).first()
        return None if row is None else _from_row(row)

    def get(self, snapshot_id: str) -> PerformanceSnapshot:
        row = self._session.get(PerformanceSnapshotRow, snapshot_id)
        if row is None:
            raise NotFoundError("performance_snapshot", snapshot_id)
        return _from_row(row)

    def list_for_post(self, post_id: str) -> list[PerformanceSnapshot]:
        stmt = (
            select(PerformanceSnapshotRow)
            .where(PerformanceSnapshotRow.post_id == post_id)
            .order_by(PerformanceSnapshotRow.age_hours)
        )
        return [_from_row(r) for r in self._session.scalars(stmt)]

    def list_for_account(
        self, *, account_id: str, platform: PublishPlatform, limit: int = 2000
    ) -> list[PerformanceSnapshot]:
        stmt = (
            select(PerformanceSnapshotRow)
            .where(
                PerformanceSnapshotRow.account_id == account_id,
                PerformanceSnapshotRow.platform == str(platform),
            )
            .order_by(PerformanceSnapshotRow.post_id, PerformanceSnapshotRow.age_hours)
            .limit(limit)
        )
        return [_from_row(r) for r in self._session.scalars(stmt)]


__all__ = ["PerformanceSnapshotRepository"]
