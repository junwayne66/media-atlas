"""创作产物 / 审核决定 / 发布任务 / 表现快照的 SQLAlchemy 表（迁移 0006）。

与 `tables.py` 共用同一个 `Base`（同一份 metadata），单独成模块只是按落地增量分文件。

约定同 `tables.py`：列只放过滤/唯一性所需字段，完整合同对象进 payload JSONB。
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from videoforge_persistence.tables import Base


class CreativeDocumentRow(Base):
    """一份创作产物的某个版本（brief / claim_table / script_version /
    creative_timeline / render_manifest）。

    payload 是既有合同对象的 JSON（本层不新增合同）。(project_id, kind, doc_version) 唯一，
    doc_version 在项目内按 kind 单调递增——UI 能按版本回看，改一版不覆盖旧版。
    """

    __tablename__ = "creative_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    doc_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    cache_key: Mapped[str | None] = mapped_column(String(64))
    # 护栏结论（脚本 needs_review + issues）；brief/timeline 不过是 422 不落库，故常为 None。
    status: Mapped[str | None] = mapped_column(Text)
    issues: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "uq_creative_documents_project_kind_version",
            "project_id",
            "kind",
            "doc_version",
            unique=True,
        ),
    )


class ReviewDecisionRow(Base):
    """一次审核决定（VF-501 ReviewDecision）。只增不改——审批是事实记录。"""

    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    entity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublishJobRow(Base):
    """一个幂等发布任务（VF-503 PublishJob）。

    **红线**：`payload` 整存整取完整 PublishJob，**含 attempts 列表**。attempts 里的
    `external_post_token` 是"已提交过"的 durable latch（`domain.has_submitted`），一旦
    在往返中被剥离，WAITING_FOR_HUMAN → UPLOADING 之类的恢复回路就能二次提交、真的发两次帖
    （VF-503 verifier 明确警告的落地风险）。仓储层因此不做任何字段挑选式重建。

    `row_version` 是乐观锁令牌（纯存储关注点，不进合同）：每次状态迁移 +1，并发迁移 → 409。
    """

    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    publish_metadata: Mapped[dict | None] = mapped_column(JSONB)
    # 最近一次预检的输入探针 + 报告（submit 放行前要用同一能力源重跑预检）
    media_probe: Mapped[dict | None] = mapped_column(JSONB)
    preflight_report: Mapped[dict | None] = mapped_column(JSONB)
    render_manifest_id: Mapped[str | None] = mapped_column(String(36))
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_publish_jobs_account", "account_id", "platform"),
        Index("ix_publish_jobs_external_post", "platform", "state"),
    )


class PerformanceSnapshotRow(Base):
    """一张平台表现快照（VF-601 PerformanceSnapshot）。

    (post_id, age_hours) 唯一：同一帖子同一年龄点只有一张快照，重复采集**幂等返回既有**，
    绝不覆盖也绝不写第二条（快照是不可变观测事实）。指标 null 语义在 payload 里原样保留。
    """

    __tablename__ = "performance_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    post_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    age_hours: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_performance_snapshots_account", "account_id", "platform"),
        Index("uq_performance_snapshots_post_age", "post_id", "age_hours", unique=True),
    )


__all__ = [
    "CreativeDocumentRow",
    "PerformanceSnapshotRow",
    "PublishJobRow",
    "ReviewDecisionRow",
]
