"""Task Lease 语义测试（VF-007 DoD：Lease 过期可重分配 + 幂等提交）。"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine

from videoforge_contracts import ExecutionPolicy
from videoforge_persistence import (
    LeaseLostError,
    NotFoundError,
    TaskStateError,
    WorkerRepository,
    WorkerTaskRepository,
    session_scope,
)


def _register(session, name: str) -> str:
    return WorkerRepository(session).register(
        worker_id=None,
        name=name,
        hostname="test-host",
        os="darwin",
        arch="arm64",
        capabilities=["source.discover"],
        execution_location="local",
        toolchain={},
    )


def _enqueue(
    session,
    key: str = "k1",
    capability: str = "source.discover",
    max_attempts: int = 5,
) -> str:
    return WorkerTaskRepository(session).enqueue(
        capability=capability,
        params={"q": "ai"},
        idempotency_key=key,
        max_attempts=max_attempts,
    )


def test_enqueue_idempotent_by_key(session) -> None:
    repo = WorkerTaskRepository(session)
    t1 = _enqueue(session, key="same")
    session.flush()
    t2 = _enqueue(session, key="same")
    assert t1 == t2
    assert repo.get_status(t1)["status"] == "PENDING"


def test_claim_leases_pending_task(session) -> None:
    worker = _register(session, "w1")
    task_id = _enqueue(session)
    session.flush()
    envelope = WorkerTaskRepository(session).claim(
        worker_id=worker, capabilities=["source.discover"], lease_ttl_s=60
    )
    assert envelope is not None
    assert envelope.task_id == task_id
    assert envelope.attempt == 1
    assert envelope.lease_id is not None
    assert envelope.params == {"q": "ai"}
    assert (
        WorkerTaskRepository(session).claim(worker_id=worker, capabilities=["source.discover"])
        is None
    )  # 已被租，无第二个任务


def test_full_envelope_roundtrip_and_priority_order(session) -> None:
    worker = _register(session, "w1")
    repo = WorkerTaskRepository(session)
    low = repo.enqueue(
        capability="source.discover",
        params={"platform": "douyin"},
        idempotency_key="low",
        priority=-1,
    )
    high = repo.enqueue(
        capability="source.discover",
        params={"platform": "douyin"},
        idempotency_key="high",
        execution_policy=ExecutionPolicy.LOCAL_ONLY,
        workflow_id="ingest-job-1",
        input_artifact_ids=["artifact-input"],
        output_schema_ref="schemas/stage-outcome.schema.json",
        resource_limits={"timeout_s": 30, "memory_mb": 128},
        credential_handles=["profile_01HZZZZZ"],
        priority=10,
    )
    session.flush()

    envelope = repo.claim(worker_id=worker, capabilities=["source.discover"])
    assert envelope is not None and envelope.task_id == high
    assert envelope.workflow_id == "ingest-job-1"
    assert envelope.execution_policy is ExecutionPolicy.LOCAL_ONLY
    assert envelope.input_artifact_ids == ["artifact-input"]
    assert envelope.output_schema_ref == "schemas/stage-outcome.schema.json"
    assert envelope.resource_limits is not None
    assert envelope.resource_limits.timeout_s == 30
    assert envelope.credential_handles == ["profile_01HZZZZZ"]
    assert low != high


def test_enqueue_rejects_sensitive_params_before_insert(session) -> None:
    repo = WorkerTaskRepository(session)
    with pytest.raises(ValidationError, match="明文凭据"):
        repo.enqueue(
            capability="source.discover",
            params={"headers": {"Authorization": "Bearer canary"}},
            idempotency_key="unsafe",
        )
    session.flush()
    assert repo.claim(worker_id="unused", capabilities=["source.discover"]) is None


def test_claim_filters_by_capability(session) -> None:
    _register(session, "w1")
    _enqueue(session, capability="render.compose")
    session.flush()
    assert (
        WorkerTaskRepository(session).claim(worker_id="w1", capabilities=["source.discover"])
        is None
    )


def test_expired_lease_reclaimable_by_other_worker(session) -> None:
    """DoD：Lease 过期可重分配。"""
    w1 = _register(session, "w1")
    w2 = _register(session, "w2")
    _enqueue(session)
    session.flush()
    repo = WorkerTaskRepository(session)

    first = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=0)
    assert first is not None
    session.flush()

    second = repo.claim(worker_id=w2, capabilities=["source.discover"], lease_ttl_s=60)
    assert second is not None
    assert second.task_id == first.task_id
    assert second.attempt == 2
    assert second.lease_id != first.lease_id
    assert repo.get_status(first.task_id)["leased_by"] == w2


def test_active_lease_not_reclaimable(session) -> None:
    w1 = _register(session, "w1")
    w2 = _register(session, "w2")
    _enqueue(session)
    session.flush()
    repo = WorkerTaskRepository(session)
    assert repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60) is not None
    session.flush()
    assert repo.claim(worker_id=w2, capabilities=["source.discover"]) is None


def test_renew_requires_current_lease(session) -> None:
    w1 = _register(session, "w1")
    _enqueue(session)
    session.flush()
    repo = WorkerTaskRepository(session)
    envelope = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60)
    assert envelope is not None and envelope.lease_expires_at is not None

    renewed = repo.renew(envelope.task_id, lease_id=envelope.lease_id, lease_ttl_s=120)
    assert renewed > envelope.lease_expires_at
    with pytest.raises(LeaseLostError):
        repo.renew(envelope.task_id, lease_id="stale-lease")


def test_complete_idempotent_across_reassignment(session) -> None:
    """DoD：重复提交按 task_id + output_digest 幂等（30 §5 条 7）。

    w1 租约过期后任务被 w2 重领并完成；w1 迟到的提交：
    同摘要 → 幂等吸收；不同摘要 → 冲突拒绝。
    """
    w1 = _register(session, "w1")
    w2 = _register(session, "w2")
    _enqueue(session)
    session.flush()
    repo = WorkerTaskRepository(session)

    lease1 = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=0)
    session.flush()
    lease2 = repo.claim(worker_id=w2, capabilities=["source.discover"], lease_ttl_s=60)
    assert lease1 is not None and lease2 is not None

    digest = "a" * 64
    assert (
        repo.complete(
            lease2.task_id, lease_id=lease2.lease_id, output_digest=digest, output={"ok": 1}
        )
        is True
    )

    # w1 迟到提交同样的结果：幂等，不报错不覆盖
    assert (
        repo.complete(
            lease1.task_id, lease_id=lease1.lease_id, output_digest=digest, output={"ok": 1}
        )
        is False
    )
    # w1 迟到提交不同结果：拒绝
    with pytest.raises(LeaseLostError, match="不同摘要"):
        repo.complete(
            lease1.task_id, lease_id=lease1.lease_id, output_digest="b" * 64, output={"ok": 2}
        )
    assert repo.get_status(lease1.task_id)["output"] == {"ok": 1}


def test_stale_lease_complete_rejected_before_anyone_finishes(session) -> None:
    w1 = _register(session, "w1")
    w2 = _register(session, "w2")
    _enqueue(session)
    session.flush()
    repo = WorkerTaskRepository(session)
    lease1 = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=0)
    session.flush()
    lease2 = repo.claim(worker_id=w2, capabilities=["source.discover"], lease_ttl_s=60)
    assert lease1 is not None and lease2 is not None
    with pytest.raises(LeaseLostError):
        repo.complete(lease1.task_id, lease_id=lease1.lease_id, output_digest="c" * 64, output={})


def test_fail_releases_task_for_retry(session) -> None:
    w1 = _register(session, "w1")
    _enqueue(session)
    session.flush()
    repo = WorkerTaskRepository(session)
    envelope = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60)
    assert envelope is not None
    repo.fail(envelope.task_id, lease_id=envelope.lease_id, reason="模拟执行失败")
    status = repo.get_status(envelope.task_id)
    assert status["status"] == "PENDING"
    retry = repo.claim(worker_id=w1, capabilities=["source.discover"])
    assert retry is not None
    assert retry.attempt == 2


def test_permanently_failing_task_reaches_terminal_failed(session) -> None:
    """P0 遗留：claim→fail 循环耗尽尝试后进入终态 FAILED，队列不再空转。"""
    w1 = _register(session, "w1")
    _enqueue(session, max_attempts=3)
    session.flush()
    repo = WorkerTaskRepository(session)

    for expected_attempt in (1, 2, 3):
        envelope = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60)
        assert envelope is not None, f"第 {expected_attempt} 次应仍可领取"
        assert envelope.attempt == expected_attempt
        repo.fail(envelope.task_id, lease_id=envelope.lease_id, reason="能力永久失败")
        session.flush()

    status = repo.get_status(envelope.task_id)
    assert status["status"] == "FAILED"
    assert status["attempt"] == 3
    assert status["output"]["terminal"] is True
    assert status["output"]["last_error"] == "能力永久失败"
    assert status["leased_by"] is None
    # 终态不再被领取：队列不空转
    assert repo.claim(worker_id=w1, capabilities=["source.discover"]) is None


def test_expired_lease_path_also_exhausts_attempts(session) -> None:
    """worker 挂死导致租约过期反复重领，同样消耗尝试并终态化（无需显式 fail）。"""
    w1 = _register(session, "w1")
    _enqueue(session, max_attempts=2)
    session.flush()
    repo = WorkerTaskRepository(session)

    first = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=0)
    session.flush()
    second = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=0)
    assert first is not None and second is not None and second.attempt == 2
    session.flush()

    # 第三次：尝试已耗尽 → 不发租约，就地终态
    assert repo.claim(worker_id=w1, capabilities=["source.discover"]) is None
    status = repo.get_status(first.task_id)
    assert status["status"] == "FAILED"
    assert status["output"]["attempts_exhausted"] is True
    assert "attempts exhausted" in status["output"]["last_error"]


def test_claim_skips_exhausted_task_and_serves_next(session) -> None:
    """队头任务耗尽不该挡住后面的健康任务。"""
    w1 = _register(session, "w1")
    doomed = _enqueue(session, key="doomed", max_attempts=1)
    session.flush()
    healthy = _enqueue(session, key="healthy", max_attempts=5)
    session.flush()
    repo = WorkerTaskRepository(session)

    first = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60)
    assert first is not None and first.task_id == doomed
    repo.fail(first.task_id, lease_id=first.lease_id, reason="炸了")
    session.flush()
    assert repo.get_status(doomed)["status"] == "FAILED"

    nxt = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60)
    assert nxt is not None and nxt.task_id == healthy


def test_renew_and_complete_rejected_on_terminal_task(session) -> None:
    """终态 FAILED 上的续租/提交一律拒绝（租约已释放）。"""
    w1 = _register(session, "w1")
    _enqueue(session, max_attempts=1)
    session.flush()
    repo = WorkerTaskRepository(session)
    envelope = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60)
    assert envelope is not None
    repo.fail(envelope.task_id, lease_id=envelope.lease_id, reason="炸了")
    session.flush()

    with pytest.raises(LeaseLostError):
        repo.renew(envelope.task_id, lease_id=envelope.lease_id)
    with pytest.raises(LeaseLostError):
        repo.complete(
            envelope.task_id, lease_id=envelope.lease_id, output_digest="a" * 64, output={}
        )
    assert repo.get_status(envelope.task_id)["status"] == "FAILED"


def test_cancel_invalidates_active_lease_and_is_terminal(session) -> None:
    worker = _register(session, "w1")
    task_id = _enqueue(session)
    session.flush()
    repo = WorkerTaskRepository(session)
    envelope = repo.claim(worker_id=worker, capabilities=["source.discover"])
    assert envelope is not None
    repo.cancel(task_id)
    session.flush()

    assert repo.get_status(task_id)["status"] == "CANCELLED"
    assert repo.claim(worker_id=worker, capabilities=["source.discover"]) is None
    with pytest.raises(LeaseLostError):
        repo.renew(task_id, lease_id=envelope.lease_id)
    with pytest.raises(LeaseLostError):
        repo.complete(task_id, lease_id=envelope.lease_id, output_digest="a" * 64, output={})
    with pytest.raises(TaskStateError):
        repo.cancel(task_id)


def test_requeue_recovers_failed_task(session) -> None:
    """人工恢复：FAILED → PENDING 且尝试计数清零，可重新领取。"""
    w1 = _register(session, "w1")
    _enqueue(session, max_attempts=1)
    session.flush()
    repo = WorkerTaskRepository(session)
    envelope = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60)
    assert envelope is not None
    repo.fail(envelope.task_id, lease_id=envelope.lease_id, reason="临时环境故障")
    session.flush()

    repo.requeue(envelope.task_id, max_attempts=2)
    session.flush()
    status = repo.get_status(envelope.task_id)
    assert status["status"] == "PENDING"
    assert status["attempt"] == 0
    assert status["max_attempts"] == 2

    retry = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60)
    assert retry is not None
    assert retry.task_id == envelope.task_id
    assert retry.attempt == 1


def test_requeue_only_from_failed(session) -> None:
    w1 = _register(session, "w1")
    task_id = _enqueue(session)
    session.flush()
    repo = WorkerTaskRepository(session)
    with pytest.raises(TaskStateError, match="PENDING"):
        repo.requeue(task_id)

    envelope = repo.claim(worker_id=w1, capabilities=["source.discover"], lease_ttl_s=60)
    assert envelope is not None
    with pytest.raises(TaskStateError, match="LEASED"):
        repo.requeue(task_id)

    repo.complete(task_id, lease_id=envelope.lease_id, output_digest="a" * 64, output={})
    with pytest.raises(TaskStateError, match="COMPLETED"):
        repo.requeue(task_id)
    with pytest.raises(NotFoundError):
        repo.requeue("ghost")


def test_worker_register_and_heartbeat(session) -> None:
    workers = WorkerRepository(session)
    wid = _register(session, "w1")
    session.flush()
    # 幂等重注册：同 id 更新能力
    same = workers.register(
        worker_id=wid,
        name="w1-renamed",
        hostname="test-host",
        os="darwin",
        arch="arm64",
        capabilities=["source.discover", "render.compose"],
        execution_location="local",
        toolchain={"ffmpeg": None},
    )
    assert same == wid
    workers.heartbeat(wid)
    with pytest.raises(NotFoundError):
        workers.heartbeat("ghost")


def test_two_workers_claim_100_tasks_without_duplicates(migrated_engine: Engine) -> None:
    with session_scope(migrated_engine) as session:
        worker_ids = [_register(session, f"stress-{index}") for index in (1, 2)]
        task_ids = {_enqueue(session, key=f"stress-task-{index}") for index in range(100)}

    barrier = threading.Barrier(2)
    claimed: list[str] = []
    claimed_lock = threading.Lock()

    def consume(worker_id: str) -> None:
        barrier.wait()
        misses = 0
        while misses < 5:
            with session_scope(migrated_engine) as session:
                repo = WorkerTaskRepository(session)
                envelope = repo.claim(
                    worker_id=worker_id,
                    capabilities=["source.discover"],
                    lease_ttl_s=30,
                )
                if envelope is None:
                    misses += 1
                else:
                    misses = 0
                    repo.complete(
                        envelope.task_id,
                        lease_id=envelope.lease_id,
                        output_digest="a" * 64,
                        output={"worker_id": worker_id},
                    )
                    with claimed_lock:
                        claimed.append(envelope.task_id)
            if envelope is None:
                time.sleep(0.005)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(consume, worker_ids))

    assert len(claimed) == 100
    assert set(claimed) == task_ids
