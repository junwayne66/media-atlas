"""dispatch_and_wait 的真 DB 桥接：入队后由后台 Worker 完成，派发返回其产出。"""

import threading
import time

import pytest
from sqlalchemy import Engine

from videoforge_persistence import WorkerRepository, WorkerTaskRepository, session_scope
from videoforge_temporal_worker.dispatch import WorkerTaskFailed, dispatch_and_wait
from videoforge_workflows import WorkerDispatch


def _register_worker(engine: Engine) -> str:
    with session_scope(engine) as s:
        return WorkerRepository(s).register(
            worker_id=None,
            name="test-worker",
            hostname="h",
            os="darwin",
            arch="arm64",
            capabilities=["source.discover", "render.compose"],
            execution_location="local",
            toolchain={},
        )


def _complete_next_task(engine: Engine, capability: str, output: dict) -> None:
    """模拟桌面 agent：注册后轮询领取指定能力的任务并完成。"""
    worker_id = _register_worker(engine)
    for _ in range(200):
        with session_scope(engine) as s:
            repo = WorkerTaskRepository(s)
            envelope = repo.claim(worker_id=worker_id, capabilities=[capability])
            if envelope is not None:
                repo.complete(
                    envelope.task_id,
                    lease_id=envelope.lease_id,
                    output_digest="a" * 64,
                    output=output,
                )
                return
        time.sleep(0.02)
    raise AssertionError(f"未能领取到 {capability} 任务")


def test_dispatch_waits_until_worker_completes(migrated_engine: Engine) -> None:
    heartbeats: list[str] = []
    completer = threading.Thread(
        target=_complete_next_task,
        args=(migrated_engine, "source.discover", {"provider": "source.fake", "ok": True}),
    )
    completer.start()

    result = dispatch_and_wait(
        migrated_engine,
        WorkerDispatch("source.discover", {"topic": "ai"}, "disp-1"),
        heartbeat=heartbeats.append,
        poll_interval_s=0.02,
        max_wait_s=30,
    )
    completer.join()

    assert result.output == {"provider": "source.fake", "ok": True}
    assert result.task_id
    # 任务确已入队并被消费
    with session_scope(migrated_engine) as s:
        assert WorkerTaskRepository(s).get_status(result.task_id)["status"] == "COMPLETED"


def test_dispatch_enqueue_is_idempotent_on_retry(migrated_engine: Engine) -> None:
    """Activity 重试时同 key 不重复入队：先入队一个，再调 dispatch 应复用同任务。"""
    with session_scope(migrated_engine) as s:
        first = WorkerTaskRepository(s).enqueue(
            capability="render.compose", params={}, idempotency_key="disp-retry"
        )

    completer = threading.Thread(
        target=_complete_next_task,
        args=(migrated_engine, "render.compose", {"rendered": True}),
    )
    completer.start()
    result = dispatch_and_wait(
        migrated_engine,
        WorkerDispatch("render.compose", {}, "disp-retry"),
        heartbeat=lambda _tid: None,
        poll_interval_s=0.02,
        max_wait_s=30,
    )
    completer.join()
    assert result.task_id == first  # 复用既有任务，未新建
    assert result.output == {"rendered": True}


def _burn_attempts(engine: Engine, capability: str, times: int) -> None:
    """模拟永久失败的能力：领取后立刻 fail，直到尝试耗尽。"""
    worker_id = _register_worker(engine)
    burned = 0
    for _ in range(400):
        with session_scope(engine) as s:
            repo = WorkerTaskRepository(s)
            envelope = repo.claim(worker_id=worker_id, capabilities=[capability])
            if envelope is not None:
                repo.fail(envelope.task_id, lease_id=envelope.lease_id, reason="能力永久失败")
                burned += 1
                if burned >= times:
                    return
        time.sleep(0.02)
    raise AssertionError(f"未能耗尽 {capability} 的尝试（burned={burned}）")


def test_dispatch_fails_fast_when_task_reaches_terminal_failed(migrated_engine: Engine) -> None:
    """任务终态 FAILED 时派发立即失败，不等 start_to_close 超时。"""
    with session_scope(migrated_engine) as s:
        WorkerTaskRepository(s).enqueue(
            capability="source.discover",
            params={},
            idempotency_key="disp-doomed",
            max_attempts=2,
        )
    burner = threading.Thread(target=_burn_attempts, args=(migrated_engine, "source.discover", 2))
    burner.start()

    with pytest.raises(WorkerTaskFailed, match="终态失败"):
        dispatch_and_wait(
            migrated_engine,
            WorkerDispatch("source.discover", {}, "disp-doomed"),
            heartbeat=lambda _tid: None,
            poll_interval_s=0.02,
            max_wait_s=30,  # 远大于实际耗时：证明是终态触发而非超时
        )
    burner.join()

    # Temporal 语义：不可重试——重试只会再读到同一条终态任务
    with pytest.raises(WorkerTaskFailed) as exc:
        dispatch_and_wait(
            migrated_engine,
            WorkerDispatch("source.discover", {}, "disp-doomed"),
            heartbeat=lambda _tid: None,
            poll_interval_s=0.02,
            max_wait_s=5,
        )
    assert exc.value.non_retryable is True
