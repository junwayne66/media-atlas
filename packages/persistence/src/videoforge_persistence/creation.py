"""创作产物仓储（brief / claim_table / script_version / creative_timeline / render_manifest）。

产物 payload 是**既有合同对象**的 JSON（本层不新增合同），仓储只按 (project_id, kind) 做版本管理：
`add` 自动取下一个 doc_version，`latest` / `get_version` / `list` 供 UI 回看。
产物只增不改——改一版就是新 doc_version，旧版永远可回溯（README §4「编辑产生新版本」）。
"""

# 延迟注解：仓储有名为 list 的方法，会遮蔽内建 list，令后续 list[...] 注解求值失败。
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from videoforge_persistence.creation_tables import CreativeDocumentRow
from videoforge_persistence.errors import DuplicateError, NotFoundError

# 产物类别（值即列内容；与 API 路由一一对应）
DOC_BRIEF = "brief"
DOC_CLAIM_TABLE = "claim_table"
DOC_SCRIPT_VERSION = "script_version"
DOC_TIMELINE = "creative_timeline"
DOC_RENDER_MANIFEST = "render_manifest"

CREATIVE_DOCUMENT_KINDS = (
    DOC_BRIEF,
    DOC_CLAIM_TABLE,
    DOC_SCRIPT_VERSION,
    DOC_TIMELINE,
    DOC_RENDER_MANIFEST,
)


@dataclass(frozen=True)
class CreativeDocumentRecord:
    """一份创作产物的某个版本。payload 是合同对象的 JSON，仓储不解释其内容。"""

    id: str
    project_id: str
    kind: str
    doc_version: int
    payload: dict[str, Any]
    cache_key: str | None = None
    created_at: datetime | None = None


def _from_row(row: CreativeDocumentRow) -> CreativeDocumentRecord:
    return CreativeDocumentRecord(
        id=row.id,
        project_id=row.project_id,
        kind=row.kind,
        doc_version=row.doc_version,
        payload=dict(row.payload),
        cache_key=row.cache_key,
        created_at=row.created_at,
    )


class CreativeDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def next_version(self, project_id: str, kind: str) -> int:
        stmt = select(func.max(CreativeDocumentRow.doc_version)).where(
            CreativeDocumentRow.project_id == project_id,
            CreativeDocumentRow.kind == kind,
        )
        current = self._session.scalar(stmt)
        return 1 if current is None else current + 1

    def add(
        self,
        *,
        id: str,
        project_id: str,
        kind: str,
        payload: dict[str, Any],
        created_at: datetime,
        cache_key: str | None = None,
        doc_version: int | None = None,
    ) -> CreativeDocumentRecord:
        """追加一版产物；doc_version 缺省自动取下一个。"""
        version = doc_version if doc_version is not None else self.next_version(project_id, kind)
        row = CreativeDocumentRow(
            id=id,
            project_id=project_id,
            kind=kind,
            doc_version=version,
            payload=payload,
            cache_key=cache_key,
            created_at=created_at,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(
                f"creative_document 已存在: {project_id}/{kind}/v{version}"
            ) from exc
        return _from_row(row)

    def get(self, doc_id: str) -> CreativeDocumentRecord:
        row = self._session.get(CreativeDocumentRow, doc_id)
        if row is None:
            raise NotFoundError("creative_document", doc_id)
        return _from_row(row)

    def latest(self, project_id: str, kind: str) -> CreativeDocumentRecord:
        stmt = (
            select(CreativeDocumentRow)
            .where(
                CreativeDocumentRow.project_id == project_id,
                CreativeDocumentRow.kind == kind,
            )
            .order_by(CreativeDocumentRow.doc_version.desc())
            .limit(1)
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError("creative_document", f"{project_id}/{kind}")
        return _from_row(row)

    def find_latest(self, project_id: str, kind: str) -> CreativeDocumentRecord | None:
        try:
            return self.latest(project_id, kind)
        except NotFoundError:
            return None

    def get_version(self, project_id: str, kind: str, doc_version: int) -> CreativeDocumentRecord:
        stmt = select(CreativeDocumentRow).where(
            CreativeDocumentRow.project_id == project_id,
            CreativeDocumentRow.kind == kind,
            CreativeDocumentRow.doc_version == doc_version,
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError("creative_document", f"{project_id}/{kind}/v{doc_version}")
        return _from_row(row)

    def list(
        self, project_id: str, kind: str | None = None, *, limit: int = 50
    ) -> list[CreativeDocumentRecord]:
        stmt = select(CreativeDocumentRow).where(CreativeDocumentRow.project_id == project_id)
        if kind is not None:
            stmt = stmt.where(CreativeDocumentRow.kind == kind)
        stmt = stmt.order_by(
            CreativeDocumentRow.kind,
            CreativeDocumentRow.doc_version.desc(),
        ).limit(limit)
        return [_from_row(r) for r in self._session.scalars(stmt)]


__all__ = [
    "CREATIVE_DOCUMENT_KINDS",
    "DOC_BRIEF",
    "DOC_CLAIM_TABLE",
    "DOC_RENDER_MANIFEST",
    "DOC_SCRIPT_VERSION",
    "DOC_TIMELINE",
    "CreativeDocumentRecord",
    "CreativeDocumentRepository",
]
