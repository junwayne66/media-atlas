"""Task Lease 协议的持久化实现（docs/architecture/30 §5）。

关键语义：
- claim 用 FOR UPDATE SKIP LOCKED 原子领取：PENDING 或「LEASED 但租约已过期」
  的任务都可被领走——过期即可重分配，无需后台清理进程；
- renew 必须持有当前 lease_id，否则 LeaseLostError；
- complete 按 (task_id, output_digest) 幂等：同摘要重复提交返回既有结果，
  即使租约已易主；不同摘要且非持有者则拒绝。
- 尝试计数与终态 FAILED（P0 遗留补齐）：**每次 claim 消耗一次尝试**，
  故「显式 fail() 循环」与「worker 挂死 → 租约过期被重领」两种空转路径
  都被同一个计数覆盖。attempt 达到 max_attempts 后任务不再发放租约，而是
  原子转入终态 FAILED；终态不可再被 claim/renew/complete，只能人工 requeue。
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from videoforge_contracts import ExecutionPolicy, TaskEnvelope
from videoforge_contracts.ids import new_id
from videoforge_persistence.errors import DuplicateError, NotFoundError, PersistenceError
from videoforge_persistence.tables import WorkerRow, WorkerTaskRow

DEFAULT_LEASE_TTL_S = 60
DEFAULT_MAX_ATTEMPTS = 5


class LeaseLostError(PersistenceError):
    """租约不再有效：已过期被重分配、或提交摘要与已完成结果冲突。"""


class TaskStateError(PersistenceError):
    """任务当前状态不允许该操作（如对非 FAILED 任务 requeue）。"""


def _now() -> datetime:
    return datetime.now(UTC)


class WorkerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def register(
        self,
        *,
        worker_id: str | None,
        name: str,
        hostname: str,
        os: str,
        arch: str,
        capabilities: list[str],
        execution_location: str,
        toolchain: dict[str, Any],
    ) -> str:
        now = _now()
        if worker_id is not None:
            row = self._session.get(WorkerRow, worker_id)
            if row is not None:  # 重注册：幂等更新能力与工具链
                row.name = name
                row.hostname = hostname
                row.capabilities = capabilities
                row.toolchain = toolchain
                row.last_heartbeat_at = now
                return row.id
        wid = worker_id or new_id()
        self._session.add(
            WorkerRow(
                id=wid,
                name=name,
                hostname=hostname,
                os=os,
                arch=arch,
                capabilities=capabilities,
                execution_location=execution_location,
                toolchain=toolchain,
                registered_at=now,
                last_heartbeat_at=now,
            )
        )
        return wid

    def heartbeat(self, worker_id: str) -> None:
        row = self._session.get(WorkerRow, worker_id)
        if row is None:
            raise NotFoundError("worker", worker_id)
        row.last_heartbeat_at = _now()


class WorkerTaskRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(
        self,
        *,
        capability: str,
        params: dict[str, Any],
        idempotency_key: str,
        execution_policy: ExecutionPolicy = ExecutionPolicy.LOCAL_PREFERRED,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> str:
        if max_attempts < 1:
            raise ValueError("max_attempts 必须 ≥ 1")
        now = _now()
        task_id = new_id()
        # ON CONFLICT 幂等：并发同 key 入队不冲突，落败方读回既有任务 id
        stmt = (
            pg_insert(WorkerTaskRow)
            .values(
                id=task_id,
                idempotency_key=idempotency_key,
                capability=capability,
                params=params,
                execution_policy=str(execution_policy),
                status="PENDING",
                attempt=0,
                max_attempts=max_attempts,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(WorkerTaskRow.id)
        )
        inserted = self._session.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return inserted
        existing = self._session.scalar(
            select(WorkerTaskRow.id).where(WorkerTaskRow.idempotency_key == idempotency_key)
        )
        assert existing is not None
        return existing

    def claim(
        self,
        *,
        worker_id: str,
        capabilities: list[str],
        lease_ttl_s: int = DEFAULT_LEASE_TTL_S,
    ) -> TaskEnvelope | None:
        """原子领取一个任务；无可领任务返回 None。

        领取前先查尝试上限：已耗尽的候选不再发租约，而是就地转入终态 FAILED，
        然后继续找下一个候选——这样「永久失败的能力」不会一直占着队列头空转，
        也不会把上游 workflow 拖到 start_to_close 超时。
        """
        now = _now()
        while True:
            row = self._session.scalars(
                select(WorkerTaskRow)
                .where(
                    WorkerTaskRow.capability.in_(capabilities),
                    or_(
                        WorkerTaskRow.status == "PENDING",
                        and_(
                            WorkerTaskRow.status == "LEASED",
                            WorkerTaskRow.lease_expires_at < now,
                        ),
                    ),
                )
                .order_by(WorkerTaskRow.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                return None
            if row.attempt >= row.max_attempts:
                # 尝试已耗尽（含「租约过期被反复重领」路径）→ 终态，不再发租约
                self._terminate(row, f"attempts exhausted ({row.attempt}/{row.max_attempts})")
                self._session.flush()  # 让下一轮查询看不到这一行
                continue
            break
        row.status = "LEASED"
        row.lease_id = new_id()
        row.leased_by = worker_id
        row.lease_expires_at = now + timedelta(seconds=lease_ttl_s)
        row.attempt += 1
        row.updated_at = now
        return TaskEnvelope(
            task_id=row.id,
            idempotency_key=row.idempotency_key,
            capability=row.capability,
            attempt=row.attempt,
            execution_policy=ExecutionPolicy(row.execution_policy),
            lease_id=row.lease_id,
            lease_expires_at=row.lease_expires_at,
            params=row.params,
            created_at=row.created_at,
        )

    def renew(
        self, task_id: str, *, lease_id: str, lease_ttl_s: int = DEFAULT_LEASE_TTL_S
    ) -> datetime:
        """续租；任务已终态 FAILED（或租约易主）时抛 LeaseLostError。"""
        # 行锁读：防止「读到陈旧租约后他人重领」的 check-then-act 竞态
        row = self._session.get(WorkerTaskRow, task_id, with_for_update=True)
        if row is None:
            raise NotFoundError("worker_task", task_id)
        if row.status != "LEASED" or row.lease_id != lease_id:
            raise LeaseLostError(f"task {task_id} 租约已失效（可能已被重分配）")
        row.lease_expires_at = _now() + timedelta(seconds=lease_ttl_s)
        row.updated_at = _now()
        return row.lease_expires_at

    def complete(
        self,
        task_id: str,
        *,
        lease_id: str,
        output_digest: str,
        output: dict[str, Any],
    ) -> bool:
        """返回 True=本次写入结果；False=幂等命中（同摘要已完成）。

        终态 FAILED 的任务不接受提交（租约已释放）→ LeaseLostError；
        COMPLETED 的 (task_id, output_digest) 幂等语义不受尝试上限影响。
        """
        row = self._session.get(WorkerTaskRow, task_id, with_for_update=True)
        if row is None:
            raise NotFoundError("worker_task", task_id)
        if row.status == "COMPLETED":
            if row.output_digest == output_digest:
                return False  # 30 §5 条 7：task_id + output_digest 幂等
            raise LeaseLostError(
                f"task {task_id} 已由他人以不同摘要完成（{row.output_digest} != {output_digest}）"
            )
        if row.status != "LEASED" or row.lease_id != lease_id:
            raise LeaseLostError(f"task {task_id} 租约已失效，提交被拒")
        row.status = "COMPLETED"
        row.output = output
        row.output_digest = output_digest
        row.updated_at = _now()
        return True

    def fail(self, task_id: str, *, lease_id: str, reason: str) -> None:
        """执行失败：释放租约回 PENDING 等待重领；尝试已耗尽则直接终态 FAILED。"""
        row = self._session.get(WorkerTaskRow, task_id, with_for_update=True)
        if row is None:
            raise NotFoundError("worker_task", task_id)
        if row.status != "LEASED" or row.lease_id != lease_id:
            raise LeaseLostError(f"task {task_id} 租约已失效")
        if row.attempt >= row.max_attempts:
            # 本次即最后一次尝试 → 不再回 PENDING，避免 claim→fail 无限循环
            self._terminate(row, reason, exhausted=True)
            return
        # attempt 已在 claim 时累计，这里只释放租约
        row.status = "PENDING"
        row.lease_id = None
        row.leased_by = None
        row.lease_expires_at = None
        row.output = {"last_error": reason}
        row.updated_at = _now()

    def requeue(self, task_id: str, *, max_attempts: int | None = None) -> None:
        """人工恢复：把终态 FAILED 的任务重置尝试计数并放回 PENDING。

        只允许从 FAILED 出发——PENDING/LEASED 重置会与在途租约打架，
        COMPLETED 重置会破坏 (task_id, output_digest) 幂等语义。
        """
        row = self._session.get(WorkerTaskRow, task_id, with_for_update=True)
        if row is None:
            raise NotFoundError("worker_task", task_id)
        if row.status != "FAILED":
            raise TaskStateError(f"task {task_id} 状态为 {row.status}，只有 FAILED 可 requeue")
        if max_attempts is not None:
            if max_attempts < 1:
                raise ValueError("max_attempts 必须 ≥ 1")
            row.max_attempts = max_attempts
        row.status = "PENDING"
        row.attempt = 0
        row.lease_id = None
        row.leased_by = None
        row.lease_expires_at = None
        row.output = {"requeued_after": (row.output or {}).get("last_error")}
        row.updated_at = _now()

    def _terminate(self, row: WorkerTaskRow, reason: str, *, exhausted: bool = True) -> None:
        """转入终态 FAILED：释放租约、记录原因；此后不可被 claim。"""
        row.status = "FAILED"
        row.lease_id = None
        row.leased_by = None
        row.lease_expires_at = None
        row.output = {
            **(row.output or {}),
            "last_error": reason,
            "terminal": True,
            "attempts_exhausted": exhausted,
        }
        row.updated_at = _now()

    def get_status(self, task_id: str) -> dict[str, Any]:
        row = self._session.get(WorkerTaskRow, task_id)
        if row is None:
            raise NotFoundError("worker_task", task_id)
        return {
            "task_id": row.id,
            "status": row.status,
            "attempt": row.attempt,
            "max_attempts": row.max_attempts,
            "capability": row.capability,
            "output": row.output,
            "output_digest": row.output_digest,
            "leased_by": row.leased_by,
            "lease_expires_at": row.lease_expires_at,
        }


__all__ = [
    "DEFAULT_LEASE_TTL_S",
    "DEFAULT_MAX_ATTEMPTS",
    "DuplicateError",
    "LeaseLostError",
    "TaskStateError",
    "WorkerRepository",
    "WorkerTaskRepository",
]
