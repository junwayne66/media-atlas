"""dispatch_to_worker Activity 的实现：把 Workflow 阶段桥接到 lease 队列。

流程：入队一个 worker-task → 轮询直到桌面/云 Worker 完成 → 返回结果。
轮询期间打 Temporal heartbeat，故长等待不会触发 activity 超时；enqueue 按
idempotency_key 幂等，故 activity 重试不会重复入队。核心 dispatch_and_wait
不依赖 Temporal 运行时（heartbeat/sleep 注入），可脱离 Temporal 单测。
"""

import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine
from temporalio import activity

from videoforge_persistence import WorkerTaskRepository, session_scope
from videoforge_workflows import WorkerDispatch, WorkerDispatchResult


class DispatchTimeout(RuntimeError):
    """派发的任务在内部安全期限内未完成（防止轮询无限挂起）。"""


def dispatch_and_wait(
    engine: Engine,
    dispatch: WorkerDispatch,
    *,
    heartbeat: Callable[[str], None],
    poll_interval_s: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    max_wait_s: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> WorkerDispatchResult:
    """入队 → 轮询直到完成。

    max_wait_s=None 时不设内部期限（生产依赖 Temporal 的 start_to_close_timeout
    与 heartbeat_timeout 兜底）；测试传有限值，卡住即 DispatchTimeout 快速失败。
    """
    with session_scope(engine) as s:
        task_id = WorkerTaskRepository(s).enqueue(
            capability=dispatch.capability,
            params=dispatch.params,
            idempotency_key=dispatch.idempotency_key,
        )
    deadline = None if max_wait_s is None else monotonic() + max_wait_s
    while True:
        with session_scope(engine) as s:
            status: dict[str, Any] = WorkerTaskRepository(s).get_status(task_id)
        if status["status"] == "COMPLETED":
            return WorkerDispatchResult(task_id=task_id, output=status["output"] or {})
        if deadline is not None and monotonic() >= deadline:
            raise DispatchTimeout(
                f"task {task_id} ({dispatch.capability}) 未在 {max_wait_s}s 内完成"
            )
        heartbeat(task_id)
        sleep(poll_interval_s)


class LeaseDispatchActivities:
    """持有 DB 引擎的 Activity 容器；worker 注册 dispatch_to_worker。"""

    def __init__(self, engine: Engine, *, poll_interval_s: float = 0.5) -> None:
        self._engine = engine
        self._poll_interval_s = poll_interval_s

    @activity.defn(name="dispatch_to_worker")
    def dispatch_to_worker(self, dispatch: WorkerDispatch) -> WorkerDispatchResult:
        # 同步 Activity（线程池执行）；sync SQLAlchemy 直接用，heartbeat 走 Temporal
        return dispatch_and_wait(
            self._engine,
            dispatch,
            heartbeat=lambda task_id: activity.heartbeat(task_id),
            poll_interval_s=self._poll_interval_s,
        )
