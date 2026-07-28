"""VF-108 采集业务投影仓储。

IngestJob 是 Temporal 的查询投影，不提供 claim；所有状态变化与事件在同一事务提交。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from videoforge_contracts import (
    DiscoveryQuery,
    IngestJob,
    IngestJobEvent,
    IngestJobStatus,
    RightsAttestation,
    SourceProfile,
)
from videoforge_persistence.errors import NotFoundError, VersionConflictError
from videoforge_persistence.ingest_tables import (
    DiscoveryQueryRow,
    IngestJobEventRow,
    IngestJobRow,
    RightsAttestationRow,
    SourceProfileRow,
)

_TERMINAL = {
    IngestJobStatus.SUCCEEDED,
    IngestJobStatus.FAILED,
    IngestJobStatus.CANCELLED,
}
_ALLOWED_TRANSITIONS = {
    IngestJobStatus.PENDING: {IngestJobStatus.RUNNING, IngestJobStatus.CANCELLED},
    IngestJobStatus.RUNNING: {
        IngestJobStatus.SUCCEEDED,
        IngestJobStatus.RETRY_WAIT,
        IngestJobStatus.NEED_HUMAN,
        IngestJobStatus.FAILED,
        IngestJobStatus.CANCELLED,
    },
    IngestJobStatus.RETRY_WAIT: {
        IngestJobStatus.RUNNING,
        IngestJobStatus.FAILED,
        IngestJobStatus.CANCELLED,
    },
    IngestJobStatus.NEED_HUMAN: {
        IngestJobStatus.PENDING,
        IngestJobStatus.CANCELLED,
    },
}


class IngestStateError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _job_from_row(row: IngestJobRow) -> IngestJob:
    return IngestJob(
        id=row.id,
        schema_version=row.schema_version,
        version=row.version,
        job_type=row.job_type,
        status=row.status,
        platform=row.platform,
        idempotency_key=row.idempotency_key,
        workflow_id=row.workflow_id,
        worker_task_id=row.worker_task_id,
        source_asset_id=row.source_asset_id,
        discovery_query_id=row.discovery_query_id,
        profile_id=row.profile_id,
        attempt=row.attempt,
        max_attempts=row.max_attempts,
        payload=row.payload,
        result=row.result,
        error_code=row.error_code,
        error_message=row.error_message,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        updated_at=row.updated_at,
    )


def _event_from_row(row: IngestJobEventRow) -> IngestJobEvent:
    return IngestJobEvent(
        id=row.id,
        schema_version=row.schema_version,
        job_id=row.job_id,
        event_type=row.event_type,
        from_status=row.from_status,
        to_status=row.to_status,
        actor_id=row.actor_id,
        message=row.message,
        details=row.details,
        created_at=row.created_at,
    )


class IngestRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_query(self, query: DiscoveryQuery) -> bool:
        values = query.model_dump(mode="json")
        values["query_text"] = values.pop("query_text")
        stmt = (
            pg_insert(DiscoveryQueryRow)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(DiscoveryQueryRow.id)
        )
        return self._session.execute(stmt).scalar_one_or_none() is not None

    def create_job(self, job: IngestJob, *, event_id: str) -> tuple[IngestJob, bool]:
        values = job.model_dump(mode="json")
        stmt = (
            pg_insert(IngestJobRow)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(IngestJobRow.id)
        )
        inserted_id = self._session.execute(stmt).scalar_one_or_none()
        if inserted_id is None:
            row = self._session.scalar(
                select(IngestJobRow).where(IngestJobRow.idempotency_key == job.idempotency_key)
            )
            assert row is not None
            return _job_from_row(row), False
        self.append_event(
            IngestJobEvent(
                id=event_id,
                job_id=job.id,
                event_type="ingest.job.created",
                to_status=job.status,
                actor_id="system",
                created_at=job.created_at,
            )
        )
        return job, True

    def get_job(self, job_id: str, *, for_update: bool = False) -> IngestJob:
        if for_update:
            row = self._session.get(IngestJobRow, job_id, with_for_update=True)
        else:
            row = self._session.get(IngestJobRow, job_id)
        if row is None:
            raise NotFoundError("ingest_job", job_id)
        return _job_from_row(row)

    def transition(
        self,
        job_id: str,
        to_status: IngestJobStatus,
        *,
        event_id: str,
        event_type: str,
        actor_id: str = "system",
        expected_version: int | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        worker_task_id: str | None = None,
        attempt: int | None = None,
    ) -> IngestJob:
        # Temporal Activity 可能在“事务已提交但 ack 丢失”后重放；确定性 event id 已存在
        # 即代表该转换完成，直接返回当前投影，不能再次执行状态机。
        if self._session.get(IngestJobEventRow, event_id) is not None:
            return self.get_job(job_id)
        current = self.get_job(job_id, for_update=True)
        if expected_version is not None and current.version != expected_version:
            raise VersionConflictError("ingest_job", job_id, expected_version)
        if to_status not in _ALLOWED_TRANSITIONS.get(current.status, set()):
            raise IngestStateError(f"{current.status} -> {to_status} 非法")
        now = _now()
        values: dict[str, Any] = {
            "status": str(to_status),
            "version": current.version + 1,
            "updated_at": now,
            "result": result,
            "error_code": error_code,
            "error_message": error_message,
        }
        if current.started_at is None and to_status is IngestJobStatus.RUNNING:
            values["started_at"] = now
        if to_status in _TERMINAL:
            values["finished_at"] = now
        if worker_task_id is not None:
            values["worker_task_id"] = worker_task_id
        if attempt is not None:
            values["attempt"] = attempt
        self._session.execute(
            update(IngestJobRow).where(IngestJobRow.id == job_id).values(**values)
        )
        self.append_event(
            IngestJobEvent(
                id=event_id,
                job_id=job_id,
                event_type=event_type,
                from_status=current.status,
                to_status=to_status,
                actor_id=actor_id,
                message=message,
                details=details or {},
                created_at=now,
            )
        )
        self._session.flush()
        return self.get_job(job_id)

    def append_event(self, event: IngestJobEvent) -> bool:
        stmt = (
            pg_insert(IngestJobEventRow)
            .values(**event.model_dump(mode="json"))
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(IngestJobEventRow.id)
        )
        return self._session.execute(stmt).scalar_one_or_none() is not None

    def bind_worker_task(
        self,
        job_id: str,
        worker_task_id: str,
        *,
        event_id: str,
    ) -> IngestJob:
        """把当前 Lease task 投影到 IngestJob，便于 API 取消在途执行。

        绑定不改变业务状态；确定性 event id 使 dispatch Activity 重放保持幂等。
        """
        if self._session.get(IngestJobEventRow, event_id) is not None:
            return self.get_job(job_id)
        current = self.get_job(job_id, for_update=True)
        now = _now()
        self._session.execute(
            update(IngestJobRow)
            .where(IngestJobRow.id == job_id)
            .values(
                worker_task_id=worker_task_id,
                version=current.version + 1,
                updated_at=now,
            )
        )
        self.append_event(
            IngestJobEvent(
                id=event_id,
                job_id=job_id,
                event_type="ingest.job.worker_task_bound",
                from_status=current.status,
                to_status=current.status,
                actor_id="system",
                details={"worker_task_id": worker_task_id},
                created_at=now,
            )
        )
        self._session.flush()
        return self.get_job(job_id)

    def list_events(self, job_id: str) -> list[IngestJobEvent]:
        self.get_job(job_id)
        rows = self._session.scalars(
            select(IngestJobEventRow)
            .where(IngestJobEventRow.job_id == job_id)
            .order_by(IngestJobEventRow.created_at, IngestJobEventRow.id)
        )
        return [_event_from_row(row) for row in rows]

    def add_attestation(self, attestation: RightsAttestation) -> bool:
        stmt = (
            pg_insert(RightsAttestationRow)
            .values(**attestation.model_dump(mode="json"))
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(RightsAttestationRow.id)
        )
        return self._session.execute(stmt).scalar_one_or_none() is not None

    def add_profile(self, profile: SourceProfile) -> bool:
        values = profile.model_dump(mode="json")
        stmt = (
            pg_insert(SourceProfileRow)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["platform", "profile_key"])
            .returning(SourceProfileRow.id)
        )
        return self._session.execute(stmt).scalar_one_or_none() is not None


__all__ = ["IngestRepository", "IngestStateError"]
