from psycopg.errors import ForeignKeyViolation
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from videoforge_contracts import Artifact, Project
from videoforge_persistence.errors import DuplicateError, NotFoundError, VersionConflictError
from videoforge_persistence.mapping import (
    artifact_to_row,
    project_to_row,
    row_to_artifact,
    row_to_project,
)
from videoforge_persistence.outbox import record_event
from videoforge_persistence.tables import ArtifactRow, ProjectRow


class ProjectRepository:
    """可版本化聚合：更新走乐观锁（version 列），并在同一事务写 outbox 事件。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, project: Project) -> None:
        self._session.add(project_to_row(project))
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(f"project 已存在: {project.id}") from exc
        record_event(
            self._session,
            aggregate_type="project",
            aggregate_id=project.id,
            event_type="project.created",
            payload=project.model_dump(mode="json"),
        )

    def get(self, project_id: str) -> Project:
        row = self._session.get(ProjectRow, project_id)
        if row is None:
            raise NotFoundError("project", project_id)
        return row_to_project(row)

    def list(self, *, limit: int = 50) -> "list[Project]":
        """按创建时间倒序列出（UI 项目列表）。乐观锁/合同语义不变。"""
        stmt = (
            select(ProjectRow)
            .order_by(ProjectRow.created_at.desc(), ProjectRow.id)
            .limit(limit)
        )
        return [row_to_project(r) for r in self._session.scalars(stmt)]

    def update(self, project: Project, *, expected_version: int) -> Project:
        """expected_version 来自调用方读到的版本（API 层对应 If-Match）。

        成功后返回 version+1 的新合同对象；版本不匹配抛 VersionConflictError。
        """
        updated = project.model_copy(update={"version": expected_version + 1})
        values = updated.model_dump()
        values.pop("id")
        stmt = (
            update(ProjectRow)
            .where(ProjectRow.id == project.id, ProjectRow.version == expected_version)
            .values(**values)
        )
        if self._session.execute(stmt).rowcount != 1:
            # rowcount=0 两义：行不存在（404 语义）或版本不匹配（409/412 语义）
            if self._session.get(ProjectRow, project.id) is None:
                raise NotFoundError("project", project.id)
            raise VersionConflictError("project", project.id, expected_version)
        record_event(
            self._session,
            aggregate_type="project",
            aggregate_id=project.id,
            event_type="project.updated",
            payload=updated.model_dump(mode="json"),
        )
        return updated


class ArtifactRepository:
    """不可变记录：只增不改不删（docs/10-module-overview.md §2.1）。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, artifact: Artifact) -> None:
        self._session.add(artifact_to_row(artifact))
        try:
            self._session.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, ForeignKeyViolation):
                raise NotFoundError("project", artifact.project_id or "?") from exc
            raise DuplicateError(f"artifact 已存在: {artifact.id}") from exc

    def get(self, artifact_id: str) -> Artifact:
        row = self._session.get(ArtifactRow, artifact_id)
        if row is None:
            raise NotFoundError("artifact", artifact_id)
        return row_to_artifact(row)

    def find_by_sha256(self, sha256: str) -> list[Artifact]:
        """同哈希可能对应多条不同来源记录——去重分组，但绝不合并丢失（30 §7）。"""
        stmt = (
            select(ArtifactRow).where(ArtifactRow.sha256 == sha256).order_by(ArtifactRow.created_at)
        )
        return [row_to_artifact(r) for r in self._session.scalars(stmt)]
