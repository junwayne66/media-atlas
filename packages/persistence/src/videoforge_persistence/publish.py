"""发布任务仓储（VF-503 PublishJob 幂等状态机的持久化面）。

**红线（VF-503 verifier 明确警告）：重建 Job 绝不能剥离 attempts。**
`domain.has_submitted` 判"是否已提交过"靠的是 attempts 里的 `external_post_token`——这是跨进程、
跨恢复回路的 durable latch。若往返时只回填状态列而丢了 attempts，`WAITING_FOR_HUMAN → UPLOADING`
之类的人工恢复路径就会重新变成"可提交"，真的发出第二条帖子。因此本仓储：

- 写：`payload = job.model_dump(mode="json")` 整存（含完整 attempts）；
- 读：`PublishJob.model_validate(row.payload)` 整取（绝不逐字段挑选重建）。

更新走乐观锁 `row_version`（纯存储关注点，不进合同）：并发状态迁移冲突 → VersionConflictError。

**并发提交（verifier 实锤）**：乐观锁只保证"写回时没人插队"，挡不住两个并发请求在各自
`executor.submit()`（外部副作用）**之后**才发现冲突——Fake 靠 idempotency_key 幂等只发一帖，
真实浏览器/真机路径没有平台幂等键就是**双发**。因此状态变更必须先 `get_for_update` 取行锁，
把"读最新 → 域判定 → 外部调用 → 写回"整段串行化。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from videoforge_contracts import PublishJob, PublishPlatform, PublishState
from videoforge_persistence.creation_tables import PublishJobRow
from videoforge_persistence.errors import DuplicateError, NotFoundError, VersionConflictError


def _from_row(row: PublishJobRow) -> PublishJob:
    # 整取：payload 是完整合同 JSON，attempts 原样复原（红线）。
    return PublishJob.model_validate(row.payload)


class StoredPublishJob:
    """Job + 存储侧乐观锁令牌。`row_version` 用于下一次 update 的 CAS。"""

    __slots__ = (
        "job",
        "media_probe",
        "preflight_report",
        "publish_metadata",
        "render_manifest_id",
        "row_version",
    )

    def __init__(
        self,
        job: PublishJob,
        row_version: int,
        publish_metadata: dict[str, Any] | None = None,
        render_manifest_id: str | None = None,
        media_probe: dict[str, Any] | None = None,
        preflight_report: dict[str, Any] | None = None,
    ) -> None:
        self.job = job
        self.row_version = row_version
        self.publish_metadata = publish_metadata
        self.render_manifest_id = render_manifest_id
        self.media_probe = media_probe
        self.preflight_report = preflight_report


def _stored(row: PublishJobRow) -> StoredPublishJob:
    return StoredPublishJob(
        job=_from_row(row),
        row_version=row.row_version,
        publish_metadata=None if row.publish_metadata is None else dict(row.publish_metadata),
        render_manifest_id=row.render_manifest_id,
        media_probe=None if row.media_probe is None else dict(row.media_probe),
        preflight_report=(None if row.preflight_report is None else dict(row.preflight_report)),
    )


class PublishJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        job: PublishJob,
        *,
        publish_metadata: dict[str, Any] | None = None,
        render_manifest_id: str | None = None,
    ) -> StoredPublishJob:
        row = PublishJobRow(
            id=job.id,
            idempotency_key=job.idempotency_key,
            account_id=job.account_id,
            platform=str(job.platform),
            state=str(job.state),
            payload=job.model_dump(mode="json"),
            publish_metadata=publish_metadata,
            render_manifest_id=render_manifest_id,
            row_version=1,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(f"publish_job 已存在: {job.idempotency_key}") from exc
        return _stored(row)

    def get(self, job_id: str) -> StoredPublishJob:
        row = self._session.get(PublishJobRow, job_id)
        if row is None:
            raise NotFoundError("publish_job", job_id)
        return _stored(row)

    def get_for_update(self, job_id: str) -> StoredPublishJob:
        """取行锁后读最新状态（`SELECT … FOR UPDATE`）。

        所有会调用外部执行器的状态变更都必须走这里：并发的第二方会**阻塞在行锁上**，
        拿到锁时读到的已是对方提交后的 SUBMITTED，`can_submit` 即为 False → 409，
        `executor.submit` 一次都不会被第二次调用。
        """
        stmt = select(PublishJobRow).where(PublishJobRow.id == job_id).with_for_update()
        row = self._session.scalars(stmt).first()
        if row is None:
            raise NotFoundError("publish_job", job_id)
        return _stored(row)

    def find_by_idempotency_key(self, key: str) -> StoredPublishJob | None:
        stmt = select(PublishJobRow).where(PublishJobRow.idempotency_key == key)
        row = self._session.scalars(stmt).first()
        return None if row is None else _stored(row)

    def find_by_external_post_id(
        self, *, account_id: str, platform: PublishPlatform, external_post_id: str
    ) -> StoredPublishJob | None:
        """按外部帖子 ID 反查 Job（效果归因把快照挂回发布任务时用）。"""
        stmt = select(PublishJobRow).where(
            PublishJobRow.account_id == account_id,
            PublishJobRow.platform == str(platform),
            PublishJobRow.payload["external_post_id"].astext == external_post_id,
        )
        row = self._session.scalars(stmt).first()
        return None if row is None else _stored(row)

    def update(
        self,
        job: PublishJob,
        *,
        expected_row_version: int,
        media_probe: dict[str, Any] | None = None,
        preflight_report: dict[str, Any] | None = None,
    ) -> StoredPublishJob:
        """乐观锁写回。payload 整存（含 attempts），行版本 +1。

        `media_probe` / `preflight_report` 传 None 表示**保持原值不变**（只有预检端点会写）。
        """
        next_version = expected_row_version + 1
        values: dict[str, Any] = {
            "state": str(job.state),
            "payload": job.model_dump(mode="json"),
            "row_version": next_version,
            "updated_at": job.updated_at,
        }
        if media_probe is not None:
            values["media_probe"] = media_probe
        if preflight_report is not None:
            values["preflight_report"] = preflight_report
        stmt = (
            update(PublishJobRow)
            .where(
                PublishJobRow.id == job.id,
                PublishJobRow.row_version == expected_row_version,
            )
            .values(**values)
            # psycopg3 下 rowcount 不可靠 → 用 RETURNING 判定是否命中
            .returning(PublishJobRow.id)
        )
        if self._session.execute(stmt).scalar_one_or_none() is None:
            if self._session.get(PublishJobRow, job.id) is None:
                raise NotFoundError("publish_job", job.id)
            raise VersionConflictError("publish_job", job.id, expected_row_version)
        row = self._session.get(PublishJobRow, job.id)
        assert row is not None  # 上面已确认命中
        self._session.refresh(row)
        return _stored(row)

    def list(
        self,
        *,
        state: PublishState | None = None,
        platform: PublishPlatform | None = None,
        account_id: str | None = None,
        limit: int = 50,
    ) -> list[StoredPublishJob]:
        stmt = select(PublishJobRow)
        if state is not None:
            stmt = stmt.where(PublishJobRow.state == str(state))
        if platform is not None:
            stmt = stmt.where(PublishJobRow.platform == str(platform))
        if account_id is not None:
            stmt = stmt.where(PublishJobRow.account_id == account_id)
        stmt = stmt.order_by(PublishJobRow.created_at.desc(), PublishJobRow.id).limit(limit)
        return [_stored(r) for r in self._session.scalars(stmt)]


__all__ = ["PublishJobRepository", "StoredPublishJob"]
