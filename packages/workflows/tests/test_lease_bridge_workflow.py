"""time-skipping：pipeline-via-lease 编排两阶段并串联数据（假 dispatch）。

真实 dispatch_to_worker（enqueue→poll→complete）在 temporal-worker 侧用
testcontainers 单测；此处只验证 Workflow 按名调用派发活动、两阶段顺序与
render 引用 source 产出。
"""

import uuid

from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from videoforge_workflows import (
    CORE_TASK_QUEUE,
    DISPATCH_ACTIVITY,
    LeasePipelineInput,
    PipelineViaLeaseWorkflow,
    WorkerDispatch,
    WorkerDispatchResult,
)

recorded: list[WorkerDispatch] = []


@activity.defn(name=DISPATCH_ACTIVITY)
async def fake_dispatch(dispatch: WorkerDispatch) -> WorkerDispatchResult:
    recorded.append(dispatch)
    return WorkerDispatchResult(
        task_id=f"task-{dispatch.capability}",
        output={"provider": f"{dispatch.capability}.fake", "echo": dispatch.params},
    )


async def test_pipeline_via_lease_orchestrates_source_then_render() -> None:
    recorded.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=CORE_TASK_QUEUE,
            workflows=[PipelineViaLeaseWorkflow],
            activities=[fake_dispatch],
        ):
            result = await env.client.execute_workflow(
                PipelineViaLeaseWorkflow.run,
                LeasePipelineInput(project_id="p1", title="P0 Exit"),
                id=f"wf-{uuid.uuid4()}",
                task_queue=CORE_TASK_QUEUE,
            )

    assert [d.capability for d in recorded] == ["source.discover", "render.compose"]
    assert result.source.task_id == "task-source.discover"
    assert result.render.task_id == "task-render.compose"
    # render 阶段确实拿到了 source 的 task_id（阶段间数据流）
    assert result.render.output["echo"]["source_task_id"] == "task-source.discover"


async def test_idempotency_keys_are_workflow_scoped() -> None:
    recorded.clear()
    workflow_id = f"wf-{uuid.uuid4()}"
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=CORE_TASK_QUEUE,
            workflows=[PipelineViaLeaseWorkflow],
            activities=[fake_dispatch],
        ):
            await env.client.execute_workflow(
                PipelineViaLeaseWorkflow.run,
                LeasePipelineInput(project_id="p1", title="t"),
                id=workflow_id,
                task_queue=CORE_TASK_QUEUE,
            )
    keys = {d.idempotency_key for d in recorded}
    assert len(keys) == 2
    assert all(k.startswith(f"{workflow_id}-") for k in keys)
    # 前缀含 run_id，仅校验 workflow 归属与阶段后缀
    assert {k.rsplit("-", 1)[1] for k in keys} == {"source", "render"}
