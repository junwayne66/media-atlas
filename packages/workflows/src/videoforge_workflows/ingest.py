"""VF-108 IngestWorkflow：Temporal 负责编排、退避、人工等待和取消。

平台 I/O 经 dispatch_to_worker 派入现有 Task Lease；持久化经命名 Activity 完成。
Workflow 本身不 import 数据库、对象存储或平台实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from videoforge_contracts import (
    ExecutionPolicy,
    IngestJobStatus,
    IngestJobType,
    StageOutcome,
    StageOutcomeStatus,
)
from videoforge_workflows.lease_bridge import (
    DISPATCH_ACTIVITY,
    WorkerDispatch,
    WorkerDispatchResult,
)

PERSIST_INGEST_ACTIVITY = "persist_ingest_stage"
_ACTIVITY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)


@dataclass
class IngestWorkflowInput:
    job_id: str
    job_type: IngestJobType
    platform: str = "douyin"
    params: dict = field(default_factory=dict)
    execution_policy: ExecutionPolicy = ExecutionPolicy.LOCAL_ONLY
    max_stage_attempts: int = 3


@dataclass
class IngestPersistRequest:
    job_id: str
    status: IngestJobStatus
    event_id: str
    event_type: str
    worker_task_id: str | None = None
    attempt: int | None = None
    outcome: dict | None = None


@dataclass
class IngestWorkflowState:
    status: IngestJobStatus
    stage: str
    attempt: int
    resume_generation: int
    error_code: str | None = None


@dataclass
class IngestWorkflowResult:
    status: IngestJobStatus
    outcome: dict = field(default_factory=dict)
    worker_task_id: str | None = None


def _capability(job_type: IngestJobType) -> str:
    return {
        IngestJobType.DISCOVERY_SEARCH: "source.discover",
        IngestJobType.CONTENT_RESOLVE: "source.resolve",
        IngestJobType.MEDIA_ACQUIRE: "source.acquire",
        IngestJobType.SESSION_CHECK: "source.metadata",
    }[job_type]


@workflow.defn(name="ingest")
class IngestWorkflow:
    def __init__(self) -> None:
        self._status = IngestJobStatus.PENDING
        self._stage = "pending"
        self._attempt = 0
        self._generation = 0
        self._resume_requested = False
        self._cancel_requested = False
        self._error_code: str | None = None

    async def _persist(
        self,
        inp: IngestWorkflowInput,
        *,
        status: IngestJobStatus,
        event_suffix: str,
        worker_task_id: str | None = None,
        outcome: StageOutcome | None = None,
    ) -> None:
        info = workflow.info()
        await workflow.execute_activity(
            PERSIST_INGEST_ACTIVITY,
            IngestPersistRequest(
                job_id=inp.job_id,
                status=status,
                event_id=(
                    f"{info.workflow_id}:{info.run_id}:g{self._generation}:"
                    f"a{self._attempt}:{event_suffix}"
                ),
                event_type=f"ingest.job.{event_suffix}",
                worker_task_id=worker_task_id,
                attempt=self._attempt,
                outcome=None if outcome is None else outcome.model_dump(mode="json"),
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=_ACTIVITY_RETRY,
        )

    async def _dispatch(
        self, inp: IngestWorkflowInput
    ) -> tuple[WorkerDispatchResult, StageOutcome]:
        info = workflow.info()
        key = (
            f"{info.workflow_id}:{info.run_id}:{_capability(inp.job_type)}:"
            f"g{self._generation}:a{self._attempt}"
        )
        result = await workflow.execute_activity(
            DISPATCH_ACTIVITY,
            WorkerDispatch(
                capability=_capability(inp.job_type),
                params={**inp.params, "job_id": inp.job_id, "platform": inp.platform},
                idempotency_key=key,
                execution_policy=inp.execution_policy,
                workflow_id=info.workflow_id,
                output_schema_ref="schemas/ingest-stage-outcome.schema.json",
                priority=10,
                max_attempts=3,
            ),
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=_ACTIVITY_RETRY,
            result_type=WorkerDispatchResult,
        )
        return result, StageOutcome.model_validate(result.output)

    @workflow.run
    async def run(self, inp: IngestWorkflowInput) -> IngestWorkflowResult:
        self._attempt = 1
        self._status = IngestJobStatus.RUNNING
        self._stage = _capability(inp.job_type)
        await self._persist(inp, status=self._status, event_suffix="running")
        if inp.job_type is IngestJobType.MEDIA_ACQUIRE and (
            inp.params.get("rights_basis")
            not in {
                "OWNED",
                "LICENSED",
                "USER_PROVIDED",
                "INTERNAL_APPROVED",
            }
            or not inp.params.get("rights_attestation_id")
        ):
            outcome = StageOutcome(
                status=StageOutcomeStatus.PERMANENT_ERROR,
                error_code="RIGHTS_REQUIRED",
                message="媒体获取必须先提交允许的使用依据",
            )
            self._status = IngestJobStatus.FAILED
            self._stage = "rights_gate"
            self._error_code = outcome.error_code
            await self._persist(
                inp,
                status=self._status,
                event_suffix="rights_rejected",
                outcome=outcome,
            )
            return IngestWorkflowResult(
                status=self._status,
                outcome=outcome.model_dump(mode="json"),
            )

        while True:
            dispatched, outcome = await self._dispatch(inp)
            if self._cancel_requested:
                self._status = IngestJobStatus.CANCELLED
                self._stage = "cancelled"
                await self._persist(
                    inp,
                    status=self._status,
                    event_suffix="cancelled",
                    worker_task_id=dispatched.task_id,
                )
                return IngestWorkflowResult(status=self._status)

            if outcome.status in {
                StageOutcomeStatus.SUCCEEDED,
                StageOutcomeStatus.EMPTY,
            }:
                self._status = IngestJobStatus.SUCCEEDED
                self._stage = "completed"
                await self._persist(
                    inp,
                    status=self._status,
                    event_suffix="succeeded",
                    worker_task_id=dispatched.task_id,
                    outcome=outcome,
                )
                return IngestWorkflowResult(
                    status=self._status,
                    outcome=outcome.model_dump(mode="json"),
                    worker_task_id=dispatched.task_id,
                )

            if (
                outcome.status is StageOutcomeStatus.RETRYABLE_ERROR
                and self._attempt < inp.max_stage_attempts
            ):
                self._status = IngestJobStatus.RETRY_WAIT
                self._error_code = outcome.error_code
                self._stage = "retry_wait"
                await self._persist(
                    inp,
                    status=self._status,
                    event_suffix="retry_wait",
                    worker_task_id=dispatched.task_id,
                    outcome=outcome,
                )
                await workflow.sleep(timedelta(seconds=outcome.retry_after_s or 5))
                self._attempt += 1
                self._status = IngestJobStatus.RUNNING
                self._stage = _capability(inp.job_type)
                await self._persist(inp, status=self._status, event_suffix="retrying")
                continue

            if outcome.status is StageOutcomeStatus.NEED_HUMAN:
                self._status = IngestJobStatus.NEED_HUMAN
                self._error_code = outcome.error_code
                self._stage = "waiting_for_human"
                await self._persist(
                    inp,
                    status=self._status,
                    event_suffix="needs_human",
                    worker_task_id=dispatched.task_id,
                    outcome=outcome,
                )
                await workflow.wait_condition(
                    lambda: self._resume_requested or self._cancel_requested
                )
                if self._cancel_requested:
                    self._status = IngestJobStatus.CANCELLED
                    self._stage = "cancelled"
                    await self._persist(
                        inp, status=self._status, event_suffix="cancelled"
                    )
                    return IngestWorkflowResult(status=self._status)
                self._resume_requested = False
                self._generation += 1
                self._attempt = 1
                self._status = IngestJobStatus.PENDING
                await self._persist(inp, status=self._status, event_suffix="resumed")
                self._status = IngestJobStatus.RUNNING
                self._stage = _capability(inp.job_type)
                await self._persist(inp, status=self._status, event_suffix="running")
                continue

            self._status = IngestJobStatus.FAILED
            self._error_code = outcome.error_code or "ATTEMPTS_EXHAUSTED"
            self._stage = "failed"
            await self._persist(
                inp,
                status=self._status,
                event_suffix="failed",
                worker_task_id=dispatched.task_id,
                outcome=outcome,
            )
            return IngestWorkflowResult(
                status=self._status,
                outcome=outcome.model_dump(mode="json"),
                worker_task_id=dispatched.task_id,
            )

    @workflow.signal
    def resume(self) -> None:
        if self._status is IngestJobStatus.NEED_HUMAN:
            self._resume_requested = True

    @workflow.signal
    def cancel(self) -> None:
        if self._status not in {
            IngestJobStatus.SUCCEEDED,
            IngestJobStatus.FAILED,
            IngestJobStatus.CANCELLED,
        }:
            self._cancel_requested = True

    @workflow.query
    def state(self) -> IngestWorkflowState:
        return IngestWorkflowState(
            status=self._status,
            stage=self._stage,
            attempt=self._attempt,
            resume_generation=self._generation,
            error_code=self._error_code,
        )


__all__ = [
    "IngestPersistRequest",
    "IngestWorkflow",
    "IngestWorkflowInput",
    "IngestWorkflowResult",
    "IngestWorkflowState",
    "PERSIST_INGEST_ACTIVITY",
]
