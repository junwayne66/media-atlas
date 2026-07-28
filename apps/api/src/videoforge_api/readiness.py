"""采集链路结构化就绪诊断（VF-108 FR-024）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import Engine, func, select

from videoforge_media_core import ObjectStore
from videoforge_persistence import session_scope
from videoforge_persistence.ingest_tables import IngestJobRow
from videoforge_persistence.tables import WorkerTaskRow


class IngestReadiness(BaseModel):
    status: str
    database: str
    object_store: str
    pending_tasks: int | None = None
    stale_leases: int | None = None
    parser_errors_24h: int | None = None
    challenges_24h: int | None = None


class ReadinessGateway(Protocol):
    def inspect(self) -> IngestReadiness: ...


class DbIngestReadinessGateway:
    def __init__(self, engine: Engine, objects: ObjectStore) -> None:
        self._engine = engine
        self._objects = objects

    def inspect(self) -> IngestReadiness:
        database = "ready"
        pending: int | None = None
        stale: int | None = None
        parser_errors: int | None = None
        challenges: int | None = None
        now = datetime.now(UTC)
        try:
            with session_scope(self._engine) as session:
                pending = session.scalar(
                    select(func.count()).select_from(WorkerTaskRow).where(
                        WorkerTaskRow.status == "PENDING"
                    )
                )
                stale = session.scalar(
                    select(func.count()).select_from(WorkerTaskRow).where(
                        WorkerTaskRow.status == "LEASED",
                        WorkerTaskRow.lease_expires_at < now,
                    )
                )
                recent = now - timedelta(hours=24)
                parser_errors = session.scalar(
                    select(func.count()).select_from(IngestJobRow).where(
                        IngestJobRow.updated_at >= recent,
                        IngestJobRow.error_code.in_(
                            {"PARSER_DRIFT", "RESULT_UNKNOWN", "PARSER_RESULT_UNKNOWN"}
                        ),
                    )
                )
                challenges = session.scalar(
                    select(func.count()).select_from(IngestJobRow).where(
                        IngestJobRow.updated_at >= recent,
                        IngestJobRow.error_code.in_(
                            {"CHALLENGE_DETECTED", "LOGIN_REQUIRED", "NEEDS_EXPANSION"}
                        ),
                    )
                )
        except Exception:
            database = "unavailable"
        object_store = "ready" if self._objects.health_check() else "unavailable"
        status = "ready" if database == object_store == "ready" else "degraded"
        return IngestReadiness(
            status=status,
            database=database,
            object_store=object_store,
            pending_tasks=pending,
            stale_leases=stale,
            parser_errors_24h=parser_errors,
            challenges_24h=challenges,
        )


router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


def get_gateway(request: Request) -> ReadinessGateway:
    return request.app.state.ingest_readiness_gateway


GatewayDep = Annotated[ReadinessGateway, Depends(get_gateway)]


@router.get("/readiness")
def ingest_readiness(gateway: GatewayDep) -> IngestReadiness:
    return gateway.inspect()


__all__ = ["DbIngestReadinessGateway", "IngestReadiness", "router"]
