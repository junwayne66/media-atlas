"""把长工作流的每个阶段派入 Worker Task Lease 队列（P0 Exit）。

这是 ADR-004 的落地雏形：Temporal Workflow 只做编排，真正的执行交给
实现同一 Task Protocol 的 Worker——桌面 Edge Agent 领取并完成。派发
Activity（dispatch_to_worker）的实现放在 temporal-worker 侧（有 persistence
访问），此处只定义纯数据合同、Activity 名与 Workflow 编排，保持 workflows
包不依赖 persistence，Workflow 代码零 I/O。
"""

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Activity 按名调用：实现与注册在 temporal-worker（apps/temporal-worker），
# 从而 workflows 包无需依赖 persistence。
DISPATCH_ACTIVITY = "dispatch_to_worker"

_DISPATCH_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)


@dataclass
class WorkerDispatch:
    """一次派发：把某能力的任务放进 lease 队列。"""

    capability: str
    params: dict = field(default_factory=dict)
    idempotency_key: str = ""


@dataclass
class WorkerDispatchResult:
    task_id: str
    output: dict = field(default_factory=dict)


@dataclass
class LeasePipelineInput:
    project_id: str
    title: str


@dataclass
class LeasePipelineResult:
    source: WorkerDispatchResult
    render: WorkerDispatchResult


@workflow.defn(name="pipeline-via-lease")
class PipelineViaLeaseWorkflow:
    """Fake Source → Fake Render：两阶段都经 lease 队列交由桌面 Worker 执行。"""

    def __init__(self) -> None:
        self._stage = "pending"

    async def _dispatch(self, capability: str, params: dict, key: str) -> WorkerDispatchResult:
        return await workflow.execute_activity(
            DISPATCH_ACTIVITY,
            WorkerDispatch(capability=capability, params=params, idempotency_key=key),
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=_DISPATCH_RETRY,
            result_type=WorkerDispatchResult,
        )

    @workflow.run
    async def run(self, inp: LeasePipelineInput) -> LeasePipelineResult:
        info = workflow.info()
        # 含 run_id：activity 重试同 run 复用同一 worker-task（幂等），而 reset/
        # 重跑（新 run）会重新执行而非命中旧 COMPLETED 结果
        prefix = f"{info.workflow_id}-{info.run_id}"

        self._stage = "dispatch_source"
        source = await self._dispatch(
            "source.discover", {"project_id": inp.project_id}, f"{prefix}-source"
        )

        # render 阶段引用 source 产出，展示阶段间数据流
        self._stage = "dispatch_render"
        render = await self._dispatch(
            "render.compose", {"source_task_id": source.task_id}, f"{prefix}-render"
        )

        self._stage = "completed"
        return LeasePipelineResult(source=source, render=render)

    @workflow.query
    def stage(self) -> str:
        return self._stage
