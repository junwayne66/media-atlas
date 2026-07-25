"""Task Lease 协议的控制面端点（docs/architecture/30 §5）。

路由是仓储的薄封装；领取/续租/提交的核心语义与测试都在
videoforge_persistence.lease。处理器为同步函数（FastAPI 线程池执行），
避免同步 SQLAlchemy 阻塞事件循环。
"""

from datetime import datetime
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from videoforge_contracts import ExecutionPolicy, TaskEnvelope
from videoforge_persistence import (
    LeaseLostError,
    NotFoundError,
    TaskStateError,
    WorkerRepository,
    WorkerTaskRepository,
    session_scope,
)
from videoforge_persistence.lease import DEFAULT_LEASE_TTL_S, DEFAULT_MAX_ATTEMPTS


class RegisterRequest(BaseModel):
    worker_id: str | None = None
    name: str = Field(min_length=1)
    hostname: str = Field(min_length=1)
    os: str = Field(min_length=1)
    arch: str = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)
    execution_location: str = Field(pattern=r"^(local|cloud|hybrid)$")
    toolchain: dict[str, Any] = Field(default_factory=dict)


class ClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)
    lease_ttl_s: int = Field(default=DEFAULT_LEASE_TTL_S, ge=1, le=3600)


class RenewRequest(BaseModel):
    lease_id: str = Field(min_length=1)
    lease_ttl_s: int = Field(default=DEFAULT_LEASE_TTL_S, ge=1, le=3600)


class CompleteRequest(BaseModel):
    lease_id: str = Field(min_length=1)
    output_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output: dict[str, Any] = Field(default_factory=dict)


class FailRequest(BaseModel):
    lease_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=2000)


class EnqueueRequest(BaseModel):
    capability: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1)
    execution_policy: ExecutionPolicy = ExecutionPolicy.LOCAL_PREFERRED
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1, le=50)


class RequeueRequest(BaseModel):
    """人工重试失败任务；max_attempts 省略则沿用原上限。"""

    max_attempts: int | None = Field(default=None, ge=1, le=50)


class WorkerGateway(Protocol):
    def register(self, request: RegisterRequest) -> str: ...

    def heartbeat(self, worker_id: str) -> None: ...

    def enqueue(self, request: EnqueueRequest) -> str: ...

    def claim(self, request: ClaimRequest) -> TaskEnvelope | None: ...

    def renew(self, task_id: str, request: RenewRequest) -> datetime: ...

    def complete(self, task_id: str, request: CompleteRequest) -> bool: ...

    def fail(self, task_id: str, request: FailRequest) -> None: ...

    def requeue(self, task_id: str, request: RequeueRequest) -> None: ...

    def task_status(self, task_id: str) -> dict[str, Any]: ...


class DbWorkerGateway:
    """每次调用一个事务边界；引擎懒连接。"""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def register(self, request: RegisterRequest) -> str:
        with session_scope(self._engine) as s:
            return WorkerRepository(s).register(
                worker_id=request.worker_id,
                name=request.name,
                hostname=request.hostname,
                os=request.os,
                arch=request.arch,
                capabilities=request.capabilities,
                execution_location=request.execution_location,
                toolchain=request.toolchain,
            )

    def heartbeat(self, worker_id: str) -> None:
        with session_scope(self._engine) as s:
            WorkerRepository(s).heartbeat(worker_id)

    def enqueue(self, request: EnqueueRequest) -> str:
        with session_scope(self._engine) as s:
            return WorkerTaskRepository(s).enqueue(
                capability=request.capability,
                params=request.params,
                idempotency_key=request.idempotency_key,
                execution_policy=request.execution_policy,
                max_attempts=request.max_attempts,
            )

    def claim(self, request: ClaimRequest) -> TaskEnvelope | None:
        with session_scope(self._engine) as s:
            return WorkerTaskRepository(s).claim(
                worker_id=request.worker_id,
                capabilities=request.capabilities,
                lease_ttl_s=request.lease_ttl_s,
            )

    def renew(self, task_id: str, request: RenewRequest) -> datetime:
        with session_scope(self._engine) as s:
            return WorkerTaskRepository(s).renew(
                task_id, lease_id=request.lease_id, lease_ttl_s=request.lease_ttl_s
            )

    def complete(self, task_id: str, request: CompleteRequest) -> bool:
        with session_scope(self._engine) as s:
            return WorkerTaskRepository(s).complete(
                task_id,
                lease_id=request.lease_id,
                output_digest=request.output_digest,
                output=request.output,
            )

    def fail(self, task_id: str, request: FailRequest) -> None:
        with session_scope(self._engine) as s:
            WorkerTaskRepository(s).fail(task_id, lease_id=request.lease_id, reason=request.reason)

    def requeue(self, task_id: str, request: RequeueRequest) -> None:
        with session_scope(self._engine) as s:
            WorkerTaskRepository(s).requeue(task_id, max_attempts=request.max_attempts)

    def task_status(self, task_id: str) -> dict[str, Any]:
        with session_scope(self._engine) as s:
            return WorkerTaskRepository(s).get_status(task_id)


router = APIRouter(prefix="/v1", tags=["workers"])


def get_gateway(request: Request) -> WorkerGateway:
    return request.app.state.worker_gateway


GatewayDep = Annotated[WorkerGateway, Depends(get_gateway)]


@router.post("/workers/register")
def register_worker(body: RegisterRequest, gateway: GatewayDep) -> dict[str, str]:
    return {"worker_id": gateway.register(body)}


@router.post("/workers/{worker_id}/heartbeat", status_code=204)
def worker_heartbeat(worker_id: str, gateway: GatewayDep) -> None:
    try:
        gateway.heartbeat(worker_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"worker 不存在: {worker_id}") from None


@router.post("/worker-tasks", status_code=202)
def enqueue_task(body: EnqueueRequest, gateway: GatewayDep) -> dict[str, str]:
    return {"task_id": gateway.enqueue(body)}


@router.post("/worker-tasks/claim")
def claim_task(body: ClaimRequest, gateway: GatewayDep) -> Response:
    envelope = gateway.claim(body)
    if envelope is None:
        return Response(status_code=204)
    return Response(
        content=envelope.model_dump_json(), media_type="application/json", status_code=200
    )


@router.post("/worker-tasks/{task_id}/renew")
def renew_lease(task_id: str, body: RenewRequest, gateway: GatewayDep) -> dict[str, str]:
    try:
        expires = gateway.renew(task_id, body)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"task 不存在: {task_id}") from None
    except LeaseLostError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"lease_expires_at": expires.isoformat()}


@router.post("/worker-tasks/{task_id}/complete")
def complete_task(task_id: str, body: CompleteRequest, gateway: GatewayDep) -> dict[str, bool]:
    try:
        stored = gateway.complete(task_id, body)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"task 不存在: {task_id}") from None
    except LeaseLostError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"stored": stored}


@router.post("/worker-tasks/{task_id}/fail", status_code=204)
def fail_task(task_id: str, body: FailRequest, gateway: GatewayDep) -> None:
    try:
        gateway.fail(task_id, body)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"task 不存在: {task_id}") from None
    except LeaseLostError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/worker-tasks/{task_id}/requeue", status_code=204)
def requeue_task(task_id: str, body: RequeueRequest, gateway: GatewayDep) -> None:
    """人工「重试失败任务」：终态 FAILED → 重置尝试计数回 PENDING（未来 UI 用）。"""
    try:
        gateway.requeue(task_id, body)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"task 不存在: {task_id}") from None
    except TaskStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/worker-tasks/{task_id}")
def task_status(task_id: str, gateway: GatewayDep) -> dict[str, Any]:
    try:
        return gateway.task_status(task_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"task 不存在: {task_id}") from None
