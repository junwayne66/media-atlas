"""Operation API：长操作不保持 HTTP 请求，返回 operation_id/workflow_id（30 §4.1）。

幂等：POST 带 Idempotency-Key，workflow id 由它派生；Temporal 对同 id 的
重复启动直接复用运行中的 Workflow。
"""

from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from videoforge_workflows import CORE_TASK_QUEUE, PipelineInput, PipelineSkeletonWorkflow


class StartOperationRequest(BaseModel):
    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1)


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")


class OperationView(BaseModel):
    operation_id: str
    running: bool
    stage: str
    waiting_for_review: bool
    result: str | None = None


class OperationsService(Protocol):
    async def start(self, idempotency_key: str, request: StartOperationRequest) -> str: ...

    async def get(self, operation_id: str) -> OperationView: ...

    async def review(self, operation_id: str, decision: str) -> None: ...


class OperationNotFound(Exception):
    pass


class TemporalOperationsService:
    def __init__(self, address: str, namespace: str = "default") -> None:
        self._address = address
        self._namespace = namespace
        self._client: Client | None = None

    async def _connect(self) -> Client:
        if self._client is None:
            self._client = await Client.connect(self._address, namespace=self._namespace)
        return self._client

    async def start(self, idempotency_key: str, request: StartOperationRequest) -> str:
        client = await self._connect()
        workflow_id = f"pipeline-{idempotency_key}"
        try:
            await client.start_workflow(
                PipelineSkeletonWorkflow.run,
                PipelineInput(project_id=request.project_id, title=request.title),
                id=workflow_id,
                task_queue=CORE_TASK_QUEUE,
            )
        except WorkflowAlreadyStartedError:
            # 同 Idempotency-Key 重复提交：复用已存在的 Workflow，不报错。
            # 注：暂不校验重复提交的 body 是否一致（骨架已知限制）
            pass
        return workflow_id

    async def get(self, operation_id: str) -> OperationView:
        client = await self._connect()
        handle = client.get_workflow_handle_for(PipelineSkeletonWorkflow.run, operation_id)
        try:
            desc = await handle.describe()
            status = await handle.query(PipelineSkeletonWorkflow.status)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise OperationNotFound(operation_id) from exc
            raise
        running = desc.status == WorkflowExecutionStatus.RUNNING
        result = None
        if desc.status == WorkflowExecutionStatus.COMPLETED:
            result = await handle.result()
        return OperationView(
            operation_id=operation_id,
            running=running,
            stage=status.stage,
            waiting_for_review=status.waiting_for_review,
            result=result,
        )

    async def review(self, operation_id: str, decision: str) -> None:
        client = await self._connect()
        handle = client.get_workflow_handle_for(PipelineSkeletonWorkflow.run, operation_id)
        try:
            await handle.signal(PipelineSkeletonWorkflow.submit_review, decision)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise OperationNotFound(operation_id) from exc
            raise


router = APIRouter(prefix="/v1/operations", tags=["operations"])


def get_operations_service(request: Request) -> OperationsService:
    return request.app.state.operations_service


ServiceDep = Annotated[OperationsService, Depends(get_operations_service)]


@router.post("", status_code=202)
async def start_operation(
    body: StartOperationRequest,
    service: ServiceDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> dict[str, str]:
    operation_id = await service.start(idempotency_key, body)
    return {"operation_id": operation_id}


@router.get("/{operation_id}")
async def get_operation(operation_id: str, service: ServiceDep) -> OperationView:
    try:
        return await service.get(operation_id)
    except OperationNotFound:
        raise HTTPException(status_code=404, detail=f"operation 不存在: {operation_id}") from None


@router.post("/{operation_id}/review", status_code=202)
async def review_operation(
    operation_id: str, body: ReviewRequest, service: ServiceDep
) -> dict[str, str]:
    try:
        await service.review(operation_id, body.decision)
    except OperationNotFound:
        raise HTTPException(status_code=404, detail=f"operation 不存在: {operation_id}") from None
    return {"operation_id": operation_id, "decision": body.decision}
