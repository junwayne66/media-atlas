"""分析链持久化：run（执行记录）+ artifact（阶段产物 + 缓存）。

产物按 (kind, cache_key) 唯一——cache_key 是 VF-201 的 activity_cache_key，命中即复用，
不再调 Provider（41 §11「换字幕不重跑下载/镜头」）。

run/artifact 不是对外交换合同（产物 payload 才是），故仓储用纯数据 dataclass 载体
（与 outbox.OutboxEvent 同样的做法），会话关闭后仍可安全使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from videoforge_persistence.errors import DuplicateError, NotFoundError
from videoforge_persistence.tables import AnalysisArtifactRow, AnalysisRunRow


@dataclass(frozen=True)
class AnalysisRunRecord:
    id: str
    project_id: str
    source_asset_id: str
    language: str
    status: str  # RUNNING / COMPLETED / FAILED
    stages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class AnalysisArtifactRecord:
    id: str
    project_id: str
    kind: str  # transcript / text_track_set / visual_analysis / video_blueprint
    cache_key: str
    payload: dict[str, Any]
    provider: str
    tool_version: str
    created_at: datetime | None = None


def _run_from_row(row: AnalysisRunRow) -> AnalysisRunRecord:
    return AnalysisRunRecord(
        id=row.id,
        project_id=row.project_id,
        source_asset_id=row.source_asset_id,
        language=row.language,
        status=row.status,
        stages=list(row.stages),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _artifact_from_row(row: AnalysisArtifactRow) -> AnalysisArtifactRecord:
    return AnalysisArtifactRecord(
        id=row.id,
        project_id=row.project_id,
        kind=row.kind,
        cache_key=row.cache_key,
        payload=dict(row.payload),
        provider=row.provider,
        tool_version=row.tool_version,
        created_at=row.created_at,
    )


class AnalysisRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, run: AnalysisRunRecord) -> None:
        self._session.add(
            AnalysisRunRow(
                id=run.id,
                project_id=run.project_id,
                source_asset_id=run.source_asset_id,
                language=run.language,
                status=run.status,
                stages=list(run.stages),
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(f"analysis_run 已存在: {run.id}") from exc

    def get(self, run_id: str) -> AnalysisRunRecord:
        row = self._session.get(AnalysisRunRow, run_id)
        if row is None:
            raise NotFoundError("analysis_run", run_id)
        return _run_from_row(row)

    def latest_for_project(self, project_id: str) -> AnalysisRunRecord:
        stmt = (
            select(AnalysisRunRow)
            .where(AnalysisRunRow.project_id == project_id)
            .order_by(AnalysisRunRow.created_at.desc(), AnalysisRunRow.id.desc())
            .limit(1)
        )
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError("analysis_run", f"project:{project_id}")
        return _run_from_row(row)


class AnalysisArtifactRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, artifact: AnalysisArtifactRecord) -> None:
        self._session.add(
            AnalysisArtifactRow(
                id=artifact.id,
                project_id=artifact.project_id,
                kind=artifact.kind,
                cache_key=artifact.cache_key,
                payload=artifact.payload,
                provider=artifact.provider,
                tool_version=artifact.tool_version,
                created_at=artifact.created_at,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(
                f"analysis_artifact 已存在: {artifact.kind}/{artifact.cache_key}"
            ) from exc

    def get(self, artifact_id: str) -> AnalysisArtifactRecord:
        row = self._session.get(AnalysisArtifactRow, artifact_id)
        if row is None:
            raise NotFoundError("analysis_artifact", artifact_id)
        return _artifact_from_row(row)

    def find_cached(self, kind: str, cache_key: str) -> AnalysisArtifactRecord | None:
        """缓存查询：命中即复用产物，调用方不再调 Provider。"""
        stmt = select(AnalysisArtifactRow).where(
            AnalysisArtifactRow.kind == kind,
            AnalysisArtifactRow.cache_key == cache_key,
        )
        row = self._session.scalars(stmt).first()
        return None if row is None else _artifact_from_row(row)


__all__ = [
    "AnalysisArtifactRecord",
    "AnalysisArtifactRepository",
    "AnalysisRunRecord",
    "AnalysisRunRepository",
]
