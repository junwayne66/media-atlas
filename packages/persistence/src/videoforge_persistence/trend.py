"""热点持久化：不可变快照（只增）+ 可版本化聚类（乐观锁 + 人工拆分/合并）。

人工拆分/合并后不被下一轮无条件覆盖（40 §10）——更新走乐观锁 version；merge
保留双方 member_item_ids 与合并理由（不丢 provenance）。
"""

# 延迟注解：仓储有名为 list 的方法，会在类体内遮蔽内建 list，令后续方法的
# list[str] 注解在定义时求值失败；PEP 563 使注解变字符串、不在定义时求值。
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from videoforge_contracts import TrendCluster, TrendItemSnapshot, TrendStage
from videoforge_contracts.ids import new_id
from videoforge_persistence.errors import NotFoundError, VersionConflictError
from videoforge_persistence.tables import TrendClusterRow, TrendItemSnapshotRow


def _now() -> datetime:
    return datetime.now(UTC)


def _cluster_from_row(row: TrendClusterRow) -> TrendCluster:
    return TrendCluster.model_validate(
        {c.name: getattr(row, c.name) for c in TrendClusterRow.__table__.columns}
    )


def _snapshot_from_row(row: TrendItemSnapshotRow) -> TrendItemSnapshot:
    return TrendItemSnapshot.model_validate(
        {c.name: getattr(row, c.name) for c in TrendItemSnapshotRow.__table__.columns}
    )


def _dedup(seq: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for x in seq:
        seen.setdefault(x, None)
    return list(seen)


class TrendItemSnapshotRepository:
    """不可变观测：只增。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, snapshot: TrendItemSnapshot) -> None:
        self._session.add(TrendItemSnapshotRow(**snapshot.model_dump()))

    def add_many(self, snapshots: list[TrendItemSnapshot]) -> None:
        self._session.add_all(TrendItemSnapshotRow(**s.model_dump()) for s in snapshots)

    def get(self, snapshot_id: str) -> TrendItemSnapshot:
        row = self._session.get(TrendItemSnapshotRow, snapshot_id)
        if row is None:
            raise NotFoundError("trend_item_snapshot", snapshot_id)
        return _snapshot_from_row(row)

    def list_by_ids(self, ids: list[str]) -> list[TrendItemSnapshot]:
        if not ids:
            return []
        stmt = (
            select(TrendItemSnapshotRow)
            .where(TrendItemSnapshotRow.id.in_(ids))
            .order_by(TrendItemSnapshotRow.observed_at)
        )
        return [_snapshot_from_row(r) for r in self._session.scalars(stmt)]


class TrendClusterRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, cluster: TrendCluster) -> None:
        self._session.add(TrendClusterRow(**cluster.model_dump()))

    def get(self, cluster_id: str) -> TrendCluster:
        row = self._session.get(TrendClusterRow, cluster_id)
        if row is None:
            raise NotFoundError("trend_cluster", cluster_id)
        return _cluster_from_row(row)

    def list(
        self,
        *,
        stage: TrendStage | None = None,
        vertical: str | None = None,
        limit: int = 50,
    ) -> list[TrendCluster]:
        stmt = select(TrendClusterRow)
        if stage is not None:
            stmt = stmt.where(TrendClusterRow.stage == str(stage))
        if vertical is not None:
            stmt = stmt.where(TrendClusterRow.vertical == vertical)
        # 热度降序，NULL 垫底；同分按 id 稳定
        stmt = stmt.order_by(
            TrendClusterRow.hot_score.desc().nullslast(), TrendClusterRow.id
        ).limit(limit)
        return [_cluster_from_row(r) for r in self._session.scalars(stmt)]

    def _apply_update(self, cluster: TrendCluster, expected_version: int) -> TrendCluster:
        updated = cluster.model_copy(update={"version": expected_version + 1, "updated_at": _now()})
        values = updated.model_dump()
        values.pop("id")
        stmt = (
            update(TrendClusterRow)
            .where(TrendClusterRow.id == cluster.id, TrendClusterRow.version == expected_version)
            .values(**values)
        )
        if self._session.execute(stmt).rowcount != 1:
            if self._session.get(TrendClusterRow, cluster.id) is None:
                raise NotFoundError("trend_cluster", cluster.id)
            raise VersionConflictError("trend_cluster", cluster.id, expected_version)
        return updated

    def update(self, cluster: TrendCluster, *, expected_version: int) -> TrendCluster:
        """乐观锁更新（对应 API If-Match）。人工编辑不被无条件覆盖。"""
        return self._apply_update(cluster, expected_version)

    def merge(
        self, target_id: str, source_id: str, *, expected_version: int, reason: str
    ) -> TrendCluster:
        """把 source 的成员/快照并入 target，保留 provenance；source 归档。"""
        if target_id == source_id:
            raise ValueError("不能把聚类并入自身")
        target = self.get(target_id)
        source = self.get(source_id)
        merged = target.model_copy(
            update={
                "member_item_ids": _dedup(target.member_item_ids + source.member_item_ids),
                "snapshot_ids": _dedup(target.snapshot_ids + source.snapshot_ids),
                "keywords": _dedup(target.keywords + source.keywords),
                "entities": _dedup(target.entities + source.entities),
                "first_seen_at": min(target.first_seen_at, source.first_seen_at),
                "last_seen_at": max(target.last_seen_at, source.last_seen_at),
                "reason_codes": _dedup([*target.reason_codes, f"MERGED_FROM:{source_id}"]),
            }
        )
        updated_target = self._apply_update(merged, expected_version)
        # source 归档而非删除（保留历史，31 §3：FAILED/归档不是删除）
        archived = source.model_copy(
            update={
                "stage": TrendStage.ARCHIVED,
                "reason_codes": _dedup(
                    [*source.reason_codes, f"MERGED_INTO:{target_id}: {reason}"]
                ),
            }
        )
        self._apply_update(archived, source.version)
        return updated_target

    def split(
        self,
        cluster_id: str,
        member_item_ids: list[str],
        *,
        expected_version: int,
        new_title: str,
        new_canonical_topic: str,
    ) -> tuple[TrendCluster, TrendCluster]:
        """把选定成员拆到新聚类；原聚类移除这些成员。二者都保留。"""
        original = self.get(cluster_id)
        split_set = set(member_item_ids)
        if not split_set:
            raise ValueError("拆分成员不能为空")
        if not split_set.issubset(set(original.member_item_ids)):
            raise ValueError("拆分成员必须是原聚类的子集")
        if split_set == set(original.member_item_ids):
            raise ValueError("不能拆走全部成员（等于改名）")

        # 按 item_id 把快照分派到两侧：被拆走成员的快照跟去新聚类，其余留原聚类，
        # 否则原聚类会继续把已离开成员的数据计入热度、新聚类却无证据重算为全零
        item_of = dict(
            self._session.execute(
                select(TrendItemSnapshotRow.id, TrendItemSnapshotRow.item_id).where(
                    TrendItemSnapshotRow.id.in_(original.snapshot_ids)
                )
            ).all()
        )
        moved_snapshots = [s for s in original.snapshot_ids if item_of.get(s) in split_set]
        kept_snapshots = [s for s in original.snapshot_ids if item_of.get(s) not in split_set]

        remaining = [m for m in original.member_item_ids if m not in split_set]
        kept = original.model_copy(
            update={
                "member_item_ids": remaining,
                "snapshot_ids": kept_snapshots,
                "reason_codes": _dedup([*original.reason_codes, "SPLIT_APPLIED"]),
            }
        )
        updated_original = self._apply_update(kept, expected_version)

        now = _now()
        new_cluster = TrendCluster(
            id=new_id(),
            title=new_title,
            canonical_topic=new_canonical_topic,
            keywords=original.keywords,
            entities=original.entities,
            member_item_ids=list(member_item_ids),
            snapshot_ids=moved_snapshots,
            first_seen_at=original.first_seen_at,
            last_seen_at=original.last_seen_at,
            stage=TrendStage.EMERGING,
            source_confidence=original.source_confidence,
            vertical=original.vertical,
            reason_codes=[f"SPLIT_FROM:{cluster_id}"],
            created_at=now,
            updated_at=now,
        )
        self.create(new_cluster)
        return updated_original, new_cluster


__all__ = ["TrendClusterRepository", "TrendItemSnapshotRepository"]
