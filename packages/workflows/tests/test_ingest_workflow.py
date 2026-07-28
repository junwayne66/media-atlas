import asyncio
import uuid

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from videoforge_contracts import (
    IngestJobStatus,
    IngestJobType,
    StageOutcome,
    StageOutcomeStatus,
)
from videoforge_workflows import (
    CORE_TASK_QUEUE,
    DISPATCH_ACTIVITY,
    PERSIST_INGEST_ACTIVITY,
    IngestPersistRequest,
    IngestWorkflow,
    IngestWorkflowInput,
    WorkerDispatch,
    WorkerDispatchResult,
)

dispatches: list[WorkerDispatch] = []
persisted: list[IngestPersistRequest] = []
outcomes: list[StageOutcome] = []


@activity.defn(name=DISPATCH_ACTIVITY)
async def fake_dispatch(dispatch: WorkerDispatch) -> WorkerDispatchResult:
    dispatches.append(dispatch)
    outcome = outcomes.pop(0)
    return WorkerDispatchResult(
        task_id=f"task-{len(dispatches)}",
        output=outcome.model_dump(mode="json"),
    )


@activity.defn(name=PERSIST_INGEST_ACTIVITY)
async def fake_persist(request: IngestPersistRequest) -> None:
    persisted.append(request)


def _reset(*planned: StageOutcome) -> None:
    dispatches.clear()
    persisted.clear()
    outcomes[:] = list(planned)


async def _execute(inp: IngestWorkflowInput):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=CORE_TASK_QUEUE,
            workflows=[IngestWorkflow],
            activities=[fake_dispatch, fake_persist],
        ):
            return await env.client.execute_workflow(
                IngestWorkflow.run,
                inp,
                id=f"ingest-{uuid.uuid4()}",
                task_queue=CORE_TASK_QUEUE,
            )


async def test_discover_success_and_empty_are_terminal_success() -> None:
    for status in (StageOutcomeStatus.SUCCEEDED, StageOutcomeStatus.EMPTY):
        _reset(StageOutcome(status=status, result={"result_count": 0}))
        result = await _execute(
            IngestWorkflowInput(
                job_id="job-1",
                job_type=IngestJobType.DISCOVERY_SEARCH,
                params={"query": "ai"},
            )
        )
        assert result.status is IngestJobStatus.SUCCEEDED
        assert dispatches[0].capability == "source.discover"
        assert dispatches[0].workflow_id is not None
        assert [item.status for item in persisted] == [
            IngestJobStatus.RUNNING,
            IngestJobStatus.SUCCEEDED,
        ]


async def test_resolve_uses_scoped_idempotency_key() -> None:
    _reset(
        StageOutcome(
            status=StageOutcomeStatus.SUCCEEDED,
            result={"source": {"content_id": "7412345678901234567"}},
        )
    )
    await _execute(
        IngestWorkflowInput(
            job_id="job-resolve",
            job_type=IngestJobType.CONTENT_RESOLVE,
            params={"url": "https://www.douyin.com/video/7412345678901234567"},
        )
    )
    dispatch = dispatches[0]
    assert dispatch.capability == "source.resolve"
    assert ":source.resolve:g0:a1" in dispatch.idempotency_key


async def test_retryable_outcome_uses_temporal_timer_then_succeeds() -> None:
    _reset(
        StageOutcome(
            status=StageOutcomeStatus.RETRYABLE_ERROR,
            error_code="RATE_LIMITED",
            retry_after_s=120,
        ),
        StageOutcome(status=StageOutcomeStatus.SUCCEEDED, result={"ok": True}),
    )
    result = await _execute(
        IngestWorkflowInput(
            job_id="job-retry",
            job_type=IngestJobType.DISCOVERY_SEARCH,
            params={"query": "ai"},
        )
    )
    assert result.status is IngestJobStatus.SUCCEEDED
    assert len(dispatches) == 2
    assert dispatches[0].idempotency_key != dispatches[1].idempotency_key
    assert [item.status for item in persisted] == [
        IngestJobStatus.RUNNING,
        IngestJobStatus.RETRY_WAIT,
        IngestJobStatus.RUNNING,
        IngestJobStatus.SUCCEEDED,
    ]


async def test_acquire_rights_gate_runs_before_dispatch() -> None:
    _reset()
    result = await _execute(
        IngestWorkflowInput(
            job_id="job-acquire-denied",
            job_type=IngestJobType.MEDIA_ACQUIRE,
            params={
                "source_asset_id": "source-1",
                "rights_basis": "UNKNOWN",
            },
        )
    )
    assert result.status is IngestJobStatus.FAILED
    assert result.outcome["error_code"] == "RIGHTS_REQUIRED"
    assert dispatches == []
    assert [item.status for item in persisted] == [
        IngestJobStatus.RUNNING,
        IngestJobStatus.FAILED,
    ]


async def test_challenge_waits_for_explicit_resume_and_changes_generation() -> None:
    _reset(
        StageOutcome(
            status=StageOutcomeStatus.NEED_HUMAN,
            error_code="CHALLENGE_DETECTED",
        ),
        StageOutcome(status=StageOutcomeStatus.SUCCEEDED, result={"ok": True}),
    )
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=CORE_TASK_QUEUE,
            workflows=[IngestWorkflow],
            activities=[fake_dispatch, fake_persist],
        ):
            handle = await env.client.start_workflow(
                IngestWorkflow.run,
                IngestWorkflowInput(
                    job_id="job-challenge",
                    job_type=IngestJobType.DISCOVERY_SEARCH,
                    params={"query": "ai"},
                ),
                id=f"ingest-{uuid.uuid4()}",
                task_queue=CORE_TASK_QUEUE,
            )
            for _ in range(100):
                state = await handle.query(IngestWorkflow.state)
                if state.status is IngestJobStatus.NEED_HUMAN:
                    break
                await asyncio.sleep(0.01)
            assert state.status is IngestJobStatus.NEED_HUMAN
            assert len(dispatches) == 1
            await handle.signal(IngestWorkflow.resume)
            result = await handle.result()
    assert result.status is IngestJobStatus.SUCCEEDED
    assert len(dispatches) == 2
    assert ":g0:a1" in dispatches[0].idempotency_key
    assert ":g1:a1" in dispatches[1].idempotency_key


async def test_challenge_can_be_cancelled_without_redispatch() -> None:
    _reset(
        StageOutcome(
            status=StageOutcomeStatus.NEED_HUMAN,
            error_code="LOGIN_REQUIRED",
        )
    )
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=CORE_TASK_QUEUE,
            workflows=[IngestWorkflow],
            activities=[fake_dispatch, fake_persist],
        ):
            handle = await env.client.start_workflow(
                IngestWorkflow.run,
                IngestWorkflowInput(
                    job_id="job-cancel",
                    job_type=IngestJobType.DISCOVERY_SEARCH,
                ),
                id=f"ingest-{uuid.uuid4()}",
                task_queue=CORE_TASK_QUEUE,
            )
            for _ in range(100):
                state = await handle.query(IngestWorkflow.state)
                if state.status is IngestJobStatus.NEED_HUMAN:
                    break
                await asyncio.sleep(0.01)
            await handle.signal(IngestWorkflow.cancel)
            result = await handle.result()
    assert result.status is IngestJobStatus.CANCELLED
    assert len(dispatches) == 1
    assert persisted[-1].status is IngestJobStatus.CANCELLED


async def test_permanent_error_is_not_retried() -> None:
    _reset(
        StageOutcome(
            status=StageOutcomeStatus.PERMANENT_ERROR,
            error_code="PARSER_DRIFT",
        )
    )
    result = await _execute(
        IngestWorkflowInput(
            job_id="job-drift",
            job_type=IngestJobType.DISCOVERY_SEARCH,
        )
    )
    assert result.status is IngestJobStatus.FAILED
    assert len(dispatches) == 1
