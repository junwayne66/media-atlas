"""可恢复采集任务 API（VF-108）。

HTTP 只创建/查询业务投影并向 Temporal 发信号；执行任务仍统一进入 Worker Task
Lease。首版只允许离线 Douyin Fixture 和纯 URL 解析，不接触真实账号或平台网络。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from videoforge_contracts import (
    DiscoveryQuery,
    IngestJob,
    IngestJobEvent,
    IngestJobStatus,
    IngestJobType,
    RightsAttestation,
    RightsBasis,
)
from videoforge_contracts.ids import new_id
from videoforge_persistence import (
    IngestRepository,
    NotFoundError,
    SourceAssetRepository,
    TaskStateError,
    WorkerTaskRepository,
    session_scope,
)
from videoforge_workflows import CORE_TASK_QUEUE, IngestWorkflow, IngestWorkflowInput

_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")
_FIXTURES = {
    "board": "board_response.json",
    "challenge": "challenge_response.json",
    "drift": "drift_response.json",
    "empty": "empty_response.json",
    "manual": "manual_import.json",
}
_TERMINAL = {
    IngestJobStatus.SUCCEEDED,
    IngestJobStatus.FAILED,
    IngestJobStatus.CANCELLED,
}


class DiscoveryStartRequest(BaseModel):
    platform: Literal["douyin"] = "douyin"
    query: str = Field(min_length=1, max_length=200)
    max_items: int = Field(default=30, ge=1, le=200)
    max_scrolls: int = Field(default=12, ge=1, le=100)
    idle_rounds: int = Field(default=3, ge=1, le=20)
    time_budget_s: int = Field(default=60, ge=1, le=600)
    profile_id: str | None = None
    fixture: Literal["board", "empty", "drift", "challenge", "manual"] = "board"

    @field_validator("profile_id")
    @classmethod
    def profile_id_is_opaque(cls, value: str | None) -> str | None:
        if value is not None and not _OPAQUE_ID_RE.fullmatch(value):
            raise ValueError("profile_id 必须是不含路径/协议语义的不透明 ID")
        return value


class ResolveStartRequest(BaseModel):
    platform: Literal["douyin"] = "douyin"
    url: str = Field(min_length=1, max_length=2048)
    profile_id: str | None = None

    @field_validator("url")
    @classmethod
    def douyin_https_url_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or (parsed.hostname or "").lower() not in {"www.douyin.com", "v.douyin.com"}
        ):
            raise ValueError("只接受无 userinfo 的 Douyin HTTPS 地址")
        return value

    @field_validator("profile_id")
    @classmethod
    def profile_id_is_opaque(cls, value: str | None) -> str | None:
        if value is not None and not _OPAQUE_ID_RE.fullmatch(value):
            raise ValueError("profile_id 必须是不含路径/协议语义的不透明 ID")
        return value


class AcquisitionStartRequest(BaseModel):
    rights_basis: RightsBasis
    rights_note: str | None = Field(default=None, max_length=1000)
    actor_id: str = Field(default="local-user", min_length=1, max_length=200)
    force: bool = False
    fixture: Literal["synthetic_mp4"] = "synthetic_mp4"


class IngestJobAccepted(BaseModel):
    job_id: str
    workflow_id: str
    job_type: IngestJobType
    status: IngestJobStatus
    created: bool = True


class IngestControlError(RuntimeError):
    pass


class IngestService(Protocol):
    async def start_discovery(
        self, idempotency_key: str, request: DiscoveryStartRequest
    ) -> IngestJob: ...

    async def start_resolve(
        self, idempotency_key: str, request: ResolveStartRequest
    ) -> IngestJob: ...

    async def start_acquisition(
        self,
        source_asset_id: str,
        idempotency_key: str,
        request: AcquisitionStartRequest,
    ) -> IngestJob: ...

    def get(self, job_id: str) -> IngestJob: ...

    def events(self, job_id: str) -> list[IngestJobEvent]: ...

    async def resume(self, job_id: str) -> IngestJob: ...

    async def cancel(self, job_id: str) -> IngestJob: ...


class DbTemporalIngestService:
    def __init__(self, engine: Engine, address: str, namespace: str = "default") -> None:
        self._engine = engine
        self._address = address
        self._namespace = namespace
        self._client: Client | None = None

    async def _connect(self) -> Client:
        if self._client is None:
            self._client = await Client.connect(self._address, namespace=self._namespace)
        return self._client

    @staticmethod
    def _query_id(idempotency_key: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"media-atlas:discovery:{idempotency_key}"))

    def _create_job(
        self,
        *,
        idempotency_key: str,
        job_type: IngestJobType,
        payload: dict,
        profile_id: str | None,
        discovery_query: DiscoveryQuery | None = None,
        source_asset_id: str | None = None,
    ) -> tuple[IngestJob, bool]:
        now = datetime.now(UTC)
        job_id = new_id()
        workflow_id = f"ingest-{job_id}"
        candidate = IngestJob(
            id=job_id,
            job_type=job_type,
            status=IngestJobStatus.PENDING,
            platform="douyin",
            idempotency_key=idempotency_key,
            workflow_id=workflow_id,
            discovery_query_id=None if discovery_query is None else discovery_query.id,
            source_asset_id=source_asset_id,
            profile_id=profile_id,
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        with session_scope(self._engine) as session:
            repo = IngestRepository(session)
            if discovery_query is not None:
                repo.create_query(discovery_query)
            return repo.create_job(candidate, event_id=f"created:{job_id}")

    async def _start_workflow(self, job: IngestJob) -> None:
        assert job.workflow_id is not None
        client = await self._connect()
        try:
            await client.start_workflow(
                IngestWorkflow.run,
                IngestWorkflowInput(
                    job_id=job.id,
                    job_type=job.job_type,
                    platform=job.platform,
                    params=job.payload,
                    max_stage_attempts=job.max_attempts,
                ),
                id=job.workflow_id,
                task_queue=CORE_TASK_QUEUE,
            )
        except WorkflowAlreadyStartedError:
            pass

    async def start_discovery(
        self, idempotency_key: str, request: DiscoveryStartRequest
    ) -> IngestJob:
        now = datetime.now(UTC)
        query = DiscoveryQuery(
            id=self._query_id(idempotency_key),
            platform=request.platform,
            query_text=request.query,
            max_items=request.max_items,
            max_scrolls=request.max_scrolls,
            idle_rounds=request.idle_rounds,
            time_budget_s=request.time_budget_s,
            profile_id=request.profile_id,
            created_at=now,
        )
        payload = {
            "query": request.query,
            "max_items": request.max_items,
            "max_scrolls": request.max_scrolls,
            "idle_rounds": request.idle_rounds,
            "time_budget_s": request.time_budget_s,
            "fixture": _FIXTURES[request.fixture],
        }
        job, _ = self._create_job(
            idempotency_key=idempotency_key,
            job_type=IngestJobType.DISCOVERY_SEARCH,
            payload=payload,
            profile_id=request.profile_id,
            discovery_query=query,
        )
        await self._start_workflow(job)
        return job

    async def start_resolve(
        self, idempotency_key: str, request: ResolveStartRequest
    ) -> IngestJob:
        job, _ = self._create_job(
            idempotency_key=idempotency_key,
            job_type=IngestJobType.CONTENT_RESOLVE,
            payload={"url": request.url},
            profile_id=request.profile_id,
        )
        await self._start_workflow(job)
        return job

    async def start_acquisition(
        self,
        source_asset_id: str,
        idempotency_key: str,
        request: AcquisitionStartRequest,
    ) -> IngestJob:
        if not request.rights_basis.permits_acquisition:
            raise IngestControlError("UNKNOWN 使用依据不能创建媒体获取任务")
        now = datetime.now(UTC)
        attestation_id = str(
            uuid5(
                NAMESPACE_URL,
                f"media-atlas:rights:{source_asset_id}:{idempotency_key}",
            )
        )
        candidate_id = new_id()
        candidate = IngestJob(
            id=candidate_id,
            job_type=IngestJobType.MEDIA_ACQUIRE,
            status=IngestJobStatus.PENDING,
            platform="douyin",
            idempotency_key=idempotency_key,
            workflow_id=f"ingest-{candidate_id}",
            source_asset_id=source_asset_id,
            payload={
                "source_asset_id": source_asset_id,
                "rights_attestation_id": attestation_id,
                "rights_basis": str(request.rights_basis),
                "force": request.force,
                "fixture": request.fixture,
            },
            created_at=now,
            updated_at=now,
        )
        with session_scope(self._engine) as session:
            source_repo = SourceAssetRepository(session)
            source = source_repo.get(source_asset_id)
            ingest_repo = IngestRepository(session)
            ingest_repo.add_attestation(
                RightsAttestation(
                    id=attestation_id,
                    source_asset_id=source_asset_id,
                    basis=request.rights_basis,
                    note=request.rights_note,
                    actor_id=request.actor_id,
                    created_at=now,
                )
            )
            if attestation_id not in source.rights_attestation_ids:
                updated = source.model_copy(
                    update={
                        "rights_basis": request.rights_basis,
                        "rights_attestation_ids": [
                            *source.rights_attestation_ids,
                            attestation_id,
                        ],
                    }
                )
                source_repo.update(updated, expected_version=source.version)
                source = updated
            job, created = ingest_repo.create_job(
                candidate, event_id=f"created:{candidate_id}"
            )
            if created and source.artifact_ids and not request.force:
                ingest_repo.transition(
                    job.id,
                    IngestJobStatus.RUNNING,
                    event_id=f"reused-running:{job.id}",
                    event_type="ingest.job.running",
                    actor_id=request.actor_id,
                )
                job = ingest_repo.transition(
                    job.id,
                    IngestJobStatus.SUCCEEDED,
                    event_id=f"reused-succeeded:{job.id}",
                    event_type="ingest.job.artifact_reused",
                    actor_id=request.actor_id,
                    result={
                        "source_asset_id": source.id,
                        "artifact_ids": source.artifact_ids,
                        "reused": True,
                    },
                )
        if job.status is IngestJobStatus.PENDING:
            await self._start_workflow(job)
        return job

    def get(self, job_id: str) -> IngestJob:
        with session_scope(self._engine) as session:
            return IngestRepository(session).get_job(job_id)

    def events(self, job_id: str) -> list[IngestJobEvent]:
        with session_scope(self._engine) as session:
            return IngestRepository(session).list_events(job_id)

    async def resume(self, job_id: str) -> IngestJob:
        job = self.get(job_id)
        if job.status is not IngestJobStatus.NEED_HUMAN:
            raise IngestControlError("只有 NEED_HUMAN 任务可以恢复")
        assert job.workflow_id is not None
        client = await self._connect()
        handle = client.get_workflow_handle_for(IngestWorkflow.run, job.workflow_id)
        try:
            await handle.signal(IngestWorkflow.resume)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise NotFoundError("ingest_workflow", job.workflow_id) from exc
            raise
        return job

    async def cancel(self, job_id: str) -> IngestJob:
        job = self.get(job_id)
        if job.status in _TERMINAL:
            raise IngestControlError("终态任务不能取消")
        if job.worker_task_id is not None:
            try:
                with session_scope(self._engine) as session:
                    WorkerTaskRepository(session).cancel(job.worker_task_id)
            except (NotFoundError, TaskStateError):
                # Workflow 信号是权威取消；worker task 可能已刚刚完成。
                pass
        assert job.workflow_id is not None
        client = await self._connect()
        handle = client.get_workflow_handle_for(IngestWorkflow.run, job.workflow_id)
        try:
            await handle.signal(IngestWorkflow.cancel)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise NotFoundError("ingest_workflow", job.workflow_id) from exc
            raise
        return job


router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


def get_ingest_service(request: Request) -> IngestService:
    return request.app.state.ingest_service


ServiceDep = Annotated[IngestService, Depends(get_ingest_service)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


def _accepted(job: IngestJob) -> IngestJobAccepted:
    assert job.workflow_id is not None
    return IngestJobAccepted(
        job_id=job.id,
        workflow_id=job.workflow_id,
        job_type=job.job_type,
        status=job.status,
    )


@router.post("/discovery", status_code=202)
async def start_discovery(
    body: DiscoveryStartRequest,
    service: ServiceDep,
    idempotency_key: IdempotencyKey,
) -> IngestJobAccepted:
    return _accepted(await service.start_discovery(idempotency_key, body))


@router.post("/resolve", status_code=202)
async def start_resolve(
    body: ResolveStartRequest,
    service: ServiceDep,
    idempotency_key: IdempotencyKey,
) -> IngestJobAccepted:
    return _accepted(await service.start_resolve(idempotency_key, body))


@router.post("/sources/{source_asset_id}/acquisitions", status_code=202)
async def start_acquisition(
    source_asset_id: str,
    body: AcquisitionStartRequest,
    service: ServiceDep,
    idempotency_key: IdempotencyKey,
) -> IngestJobAccepted:
    try:
        return _accepted(
            await service.start_acquisition(source_asset_id, idempotency_key, body)
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail=f"source asset 不存在: {source_asset_id}"
        ) from None
    except IngestControlError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/jobs/{job_id}")
def get_job(job_id: str, service: ServiceDep) -> IngestJob:
    try:
        return service.get(job_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"ingest job 不存在: {job_id}") from None


@router.get("/jobs/{job_id}/events")
def get_events(job_id: str, service: ServiceDep) -> list[IngestJobEvent]:
    try:
        return service.events(job_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"ingest job 不存在: {job_id}") from None


@router.post("/jobs/{job_id}/resume", status_code=202)
async def resume_job(job_id: str, service: ServiceDep) -> IngestJobAccepted:
    try:
        return _accepted(await service.resume(job_id))
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"ingest job 不存在: {job_id}") from None
    except IngestControlError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/jobs/{job_id}/cancel", status_code=202)
async def cancel_job(job_id: str, service: ServiceDep) -> IngestJobAccepted:
    try:
        return _accepted(await service.cancel(job_id))
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"ingest job 不存在: {job_id}") from None
    except IngestControlError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


__all__ = [
    "AcquisitionStartRequest",
    "DbTemporalIngestService",
    "DiscoveryStartRequest",
    "IngestControlError",
    "IngestJobAccepted",
    "ResolveStartRequest",
    "router",
]
