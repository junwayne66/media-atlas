"""Task Lease 协议的持久化实现（docs/architecture/30 §5）。

关键语义：
- claim 用 FOR UPDATE SKIP LOCKED 原子领取：PENDING 或「LEASED 但租约已过期」
  的任务都可被领走——过期即可重分配，无需后台清理进程；
- renew 必须持有当前 lease_id，否则 LeaseLostError；
- complete 按 (task_id, output_digest) 幂等：同摘要重复提交返回既有结果，
  即使租约已易主；不同摘要且非持有者则拒绝。
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


class LeaseLostError(PersistenceError):
    """租约不再有效：已过期被重分配、或提交摘要与已完成结果冲突。"""


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
    ) -> str:
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
        """原子领取一个任务；无可领任务返回 None。"""
        now = _now()
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
        """返回 True=本次写入结果；False=幂等命中（同摘要已完成）。"""
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
        row = self._session.get(WorkerTaskRow, task_id, with_for_update=True)
        if row is None:
            raise NotFoundError("worker_task", task_id)
        if row.status != "LEASED" or row.lease_id != lease_id:
            raise LeaseLostError(f"task {task_id} 租约已失效")
        # 失败即释放租约回 PENDING，等待重领；attempt 已在 claim 时累计
        row.status = "PENDING"
        row.lease_id = None
        row.leased_by = None
        row.lease_expires_at = None
        row.output = {"last_error": reason}
        row.updated_at = _now()

    def get_status(self, task_id: str) -> dict[str, Any]:
        row = self._session.get(WorkerTaskRow, task_id)
        if row is None:
            raise NotFoundError("worker_task", task_id)
        return {
            "task_id": row.id,
            "status": row.status,
            "attempt": row.attempt,
            "capability": row.capability,
            "output": row.output,
            "output_digest": row.output_digest,
            "leased_by": row.leased_by,
            "lease_expires_at": row.lease_expires_at,
        }


__all__ = [
    "DEFAULT_LEASE_TTL_S",
    "DuplicateError",
    "LeaseLostError",
    "WorkerRepository",
    "WorkerTaskRepository",
]
