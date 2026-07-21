"""骨架流水线 Workflow：证明长任务的四个基础能力（VF-005 DoD）。

1. 状态由 Temporal 持久化——Worker 进程重启后从断点继续；
2. 人工等待点用 Signal 恢复（WAITING_FOR_HUMAN 语义，31 §3）；
3. Query 随时可观测当前阶段；
4. Activity 带显式 retry policy 与超时。
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from videoforge_workflows.activities import analyze_source, ingest_source, render_output

DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=5,
)

_ACTIVITY_TIMEOUT = timedelta(minutes=5)

APPROVE = "approve"
REJECT = "reject"


@dataclass
class PipelineInput:
    project_id: str
    title: str


@dataclass
class PipelineStatus:
    stage: str
    waiting_for_review: bool
    review_decision: str | None


@workflow.defn(name="pipeline-skeleton")
class PipelineSkeletonWorkflow:
    def __init__(self) -> None:
        self._stage = "pending"
        self._decision: str | None = None

    @workflow.run
    async def run(self, inp: PipelineInput) -> str:
        self._stage = "ingesting"
        await workflow.execute_activity(
            ingest_source,
            inp.project_id,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY,
        )

        self._stage = "analyzing"
        await workflow.execute_activity(
            analyze_source,
            inp.project_id,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY,
        )

        # 人工等待点：不轮询、不超时自动通过；只有 Signal 能推进
        self._stage = "waiting_review"
        await workflow.wait_condition(lambda: self._decision is not None)
        if self._decision != APPROVE:
            self._stage = "rejected"
            return "REJECTED"

        self._stage = "rendering"
        await workflow.execute_activity(
            render_output,
            inp.project_id,
            start_to_close_timeout=_ACTIVITY_TIMEOUT,
            retry_policy=DEFAULT_RETRY,
        )

        self._stage = "completed"
        return "COMPLETED"

    @workflow.signal
    def submit_review(self, decision: str) -> None:
        if self._decision is None:  # 首个决定生效，重复 signal 幂等
            self._decision = decision

    @workflow.query
    def status(self) -> PipelineStatus:
        return PipelineStatus(
            stage=self._stage,
            waiting_for_review=self._stage == "waiting_review" and self._decision is None,
            review_decision=self._decision,
        )
