"""VF-005 DoD：进程重启后 Workflow 继续；人工等待可 signal 恢复。

time-skipping 测试服务器由 temporalio SDK 首次运行时自动下载。
"""

import asyncio
import uuid

from temporalio import activity
from temporalio.client import WorkflowHandle
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from videoforge_workflows import (
    ALL_ACTIVITIES,
    APPROVE,
    CORE_TASK_QUEUE,
    REJECT,
    PipelineInput,
    PipelineSkeletonWorkflow,
)

INPUT = PipelineInput(project_id="p1", title="骨架验证")


def _worker(env: WorkflowEnvironment, activities=None) -> Worker:
    return Worker(
        env.client,
        task_queue=CORE_TASK_QUEUE,
        workflows=[PipelineSkeletonWorkflow],
        activities=activities or ALL_ACTIVITIES,
        # 禁用 sticky 缓存：每个 workflow task 都从服务端历史完整重放。
        # 这正是重启语义的最强证明，也避免 worker 更替后 query 卡在
        # 旧 worker 的 sticky 队列等回退超时。
        max_cached_workflows=0,
    )


async def _wait_for_stage(handle: WorkflowHandle, stage: str, timeout_s: float = 15) -> None:
    async def _poll() -> None:
        while True:
            status = await handle.query(PipelineSkeletonWorkflow.status)
            if status.stage == stage:
                return
            await asyncio.sleep(0.05)

    await asyncio.wait_for(_poll(), timeout_s)


async def test_happy_path_signal_resumes_review_wait() -> None:
    """DoD：人工等待可 signal 恢复。"""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env):
            handle = await env.client.start_workflow(
                PipelineSkeletonWorkflow.run,
                INPUT,
                id=f"wf-{uuid.uuid4()}",
                task_queue=CORE_TASK_QUEUE,
            )
            await _wait_for_stage(handle, "waiting_review")
            status = await handle.query(PipelineSkeletonWorkflow.status)
            assert status.waiting_for_review is True

            await handle.signal(PipelineSkeletonWorkflow.submit_review, APPROVE)
            assert await handle.result() == "COMPLETED"


async def test_reject_short_circuits_render() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env):
            handle = await env.client.start_workflow(
                PipelineSkeletonWorkflow.run,
                INPUT,
                id=f"wf-{uuid.uuid4()}",
                task_queue=CORE_TASK_QUEUE,
            )
            await _wait_for_stage(handle, "waiting_review")
            await handle.signal(PipelineSkeletonWorkflow.submit_review, REJECT)
            assert await handle.result() == "REJECTED"
            status = await handle.query(PipelineSkeletonWorkflow.status)
            assert status.stage == "rejected"


async def test_workflow_survives_worker_restart() -> None:
    """DoD：进程重启后 Workflow 继续。

    第一个 Worker 推进到人审等待后整个停掉（模拟进程退出）；
    新 Worker 起来后从 Temporal 历史恢复状态，signal 仍能完成整条流水线。
    """
    async with await WorkflowEnvironment.start_time_skipping() as env:
        workflow_id = f"wf-{uuid.uuid4()}"
        async with _worker(env):
            handle = await env.client.start_workflow(
                PipelineSkeletonWorkflow.run,
                INPUT,
                id=workflow_id,
                task_queue=CORE_TASK_QUEUE,
            )
            await _wait_for_stage(handle, "waiting_review")
        # 此刻没有任何 Worker 存活——"进程已重启"

        async with _worker(env):
            handle = env.client.get_workflow_handle_for(PipelineSkeletonWorkflow.run, workflow_id)
            status = await handle.query(PipelineSkeletonWorkflow.status)
            assert status.stage == "waiting_review"  # 状态由服务端历史重建
            await handle.signal(PipelineSkeletonWorkflow.submit_review, APPROVE)
            assert await handle.result() == "COMPLETED"


async def test_activity_retry_policy_recovers_transient_failures() -> None:
    attempts = 0

    @activity.defn(name="ingest_source")
    async def flaky_ingest(project_id: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ApplicationError(f"transient failure #{attempts}")
        return f"ingested:{project_id}"

    activities = [flaky_ingest, *ALL_ACTIVITIES[1:]]
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env, activities=activities):
            handle = await env.client.start_workflow(
                PipelineSkeletonWorkflow.run,
                INPUT,
                id=f"wf-{uuid.uuid4()}",
                task_queue=CORE_TASK_QUEUE,
            )
            await _wait_for_stage(handle, "waiting_review")
            await handle.signal(PipelineSkeletonWorkflow.submit_review, APPROVE)
            assert await handle.result() == "COMPLETED"
    assert attempts == 3  # 前两次失败被 retry policy 吸收


async def test_duplicate_signals_first_decision_wins() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with _worker(env):
            handle = await env.client.start_workflow(
                PipelineSkeletonWorkflow.run,
                INPUT,
                id=f"wf-{uuid.uuid4()}",
                task_queue=CORE_TASK_QUEUE,
            )
            await _wait_for_stage(handle, "waiting_review")
            await handle.signal(PipelineSkeletonWorkflow.submit_review, APPROVE)
            await handle.signal(PipelineSkeletonWorkflow.submit_review, REJECT)
            assert await handle.result() == "COMPLETED"
