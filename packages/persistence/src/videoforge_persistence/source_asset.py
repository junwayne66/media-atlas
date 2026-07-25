"""来源素材仓储（VF-105/107 持久化面）。

只对外说合同对象（SourceAsset）；列是过滤/唯一性投影，真值在 payload JSONB。
更新走乐观锁（version），冲突抛 VersionConflictError（API 层对应 409/If-Match）。

`find_existing` 是导入幂等的依据：同一 (platform, content_id) 或同一 file_sha256 的素材
不重复建记录——重复导入返回既有资产，而不是产生第二条孤儿记录。
"""

# 延迟注解：仓储有名为 list 的方法，会遮蔽内建 list，令后续 list[...] 注解求值失败。
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from videoforge_contracts import SourceAsset, SourceDisposition
from videoforge_persistence.errors import DuplicateError, NotFoundError, VersionConflictError
from videoforge_persistence.tables import SourceAssetRow


def _now() -> datetime:
    return datetime.now(UTC)


def _to_row(asset: SourceAsset) -> SourceAssetRow:
    return SourceAssetRow(
        id=asset.id,
        schema_version=asset.schema_version,
        version=asset.version,
        kind=str(asset.kind),
        platform=asset.platform,
        content_id=asset.content_id,
        disposition=str(asset.disposition),
        file_sha256=asset.file_sha256,
        payload=asset.model_dump(mode="json"),
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _from_row(row: SourceAssetRow) -> SourceAsset:
    return SourceAsset.model_validate(row.payload)


class SourceAssetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, asset: SourceAsset) -> None:
        self._session.add(_to_row(asset))
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(f"source_asset 已存在: {asset.id}") from exc

    def get(self, asset_id: str) -> SourceAsset:
        row = self._session.get(SourceAssetRow, asset_id)
        if row is None:
            raise NotFoundError("source_asset", asset_id)
        return _from_row(row)

    def list(
        self,
        *,
        platform: str | None = None,
        disposition: SourceDisposition | None = None,
        limit: int = 50,
    ) -> list[SourceAsset]:
        stmt = select(SourceAssetRow)
        if platform is not None:
            stmt = stmt.where(SourceAssetRow.platform == platform)
        if disposition is not None:
            stmt = stmt.where(SourceAssetRow.disposition == str(disposition))
        stmt = stmt.order_by(SourceAssetRow.created_at.desc(), SourceAssetRow.id).limit(limit)
        return [_from_row(r) for r in self._session.scalars(stmt)]

    def update(self, asset: SourceAsset, *, expected_version: int) -> SourceAsset:
        """乐观锁更新；版本不匹配抛 VersionConflictError，行不存在抛 NotFoundError。"""
        updated = asset.model_copy(update={"version": expected_version + 1, "updated_at": _now()})
        row = _to_row(updated)
        values = {
            c.name: getattr(row, c.name) for c in SourceAssetRow.__table__.columns if c.name != "id"
        }
        stmt = (
            update(SourceAssetRow)
            .where(
                SourceAssetRow.id == asset.id,
                SourceAssetRow.version == expected_version,
            )
            .values(**values)
            # psycopg3 下 rowcount 不可靠 → 用 RETURNING 判定是否命中
            .returning(SourceAssetRow.id)
        )
        if self._session.execute(stmt).scalar_one_or_none() is None:
            if self._session.get(SourceAssetRow, asset.id) is None:
                raise NotFoundError("source_asset", asset.id)
            raise VersionConflictError("source_asset", asset.id, expected_version)
        return updated

    def find_existing(
        self,
        *,
        platform: str | None = None,
        content_id: str | None = None,
        file_sha256: str | None = None,
    ) -> SourceAsset | None:
        """幂等查询：优先按文件哈希（最强身份），否则按 (platform, content_id)。"""
        if file_sha256:
            stmt = (
                select(SourceAssetRow)
                .where(SourceAssetRow.file_sha256 == file_sha256)
                .order_by(SourceAssetRow.created_at, SourceAssetRow.id)
                .limit(1)
            )
            row = self._session.scalars(stmt).first()
            if row is not None:
                return _from_row(row)
        if platform and content_id:
            stmt = (
                select(SourceAssetRow)
                .where(
                    SourceAssetRow.platform == platform,
                    SourceAssetRow.content_id == content_id,
                )
                .order_by(SourceAssetRow.created_at, SourceAssetRow.id)
                .limit(1)
            )
            row = self._session.scalars(stmt).first()
            if row is not None:
                return _from_row(row)
        return None

    def list_with_file_hash(self, *, limit: int = 500) -> list[SourceAsset]:
        """有本地文件哈希的素材（去重分析的输入）。绝不删除任何来源记录（41 §5）。"""
        stmt = (
            select(SourceAssetRow)
            .where(SourceAssetRow.file_sha256.is_not(None))
            .order_by(SourceAssetRow.created_at, SourceAssetRow.id)
            .limit(limit)
        )
        return [_from_row(r) for r in self._session.scalars(stmt)]


__all__ = ["SourceAssetRepository"]
