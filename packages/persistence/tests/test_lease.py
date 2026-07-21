"""Task Lease 语义测试（VF-007 DoD：Lease 过期可重分配 + 幂等提交）。"""

import pytest

from videoforge_persistence import (
    LeaseLostError,
    NotFoundError,
    WorkerRepository,
    WorkerTaskRepository,
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


def _enqueue(session, key: str = "k1", capability: str = "source.discover") -> str:
    return WorkerTaskRepository(session).enqueue(
        capability=capability, params={"q": "ai"}, idempotency_key=key
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
