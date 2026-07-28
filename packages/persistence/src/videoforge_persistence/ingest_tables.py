"""VF-108 采集业务投影与不可变审计表。

这些表不包含 claim/run-after 字段，也没有 SKIP LOCKED 消费逻辑；真正执行仍由
worker_tasks + Temporal 驱动。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from videoforge_persistence.tables import Base


class DiscoveryQueryRow(Base):
    __tablename__ = "discovery_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    query_text: Mapped[str] = mapped_column(String(200), nullable=False)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    max_items: Mapped[int] = mapped_column(Integer, nullable=False)
    max_scrolls: Mapped[int] = mapped_column(Integer, nullable=False)
    idle_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    time_budget_s: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_id: Mapped[str | None] = mapped_column(String(36))
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IngestJobRow(Base):
    """Temporal 状态的 API 查询投影；不得作为任务队列 claim。"""

    __tablename__ = "ingest_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    job_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    workflow_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    worker_task_id: Mapped[str | None] = mapped_column(String(36))
    source_asset_id: Mapped[str | None] = mapped_column(String(36))
    discovery_query_id: Mapped[str | None] = mapped_column(ForeignKey("discovery_queries.id"))
    profile_id: Mapped[str | None] = mapped_column(String(36))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_ingest_jobs_created", "created_at", "id"),)


class IngestJobEventRow(Base):
    __tablename__ = "ingest_job_events"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("ingest_jobs.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    actor_id: Mapped[str | None] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_ingest_job_events_timeline", "job_id", "created_at", "id"),)


class RightsAttestationRow(Base):
    __tablename__ = "rights_attestations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("source_assets.id"), nullable=False, index=True
    )
    basis: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SourceProfileRow(Base):
    __tablename__ = "source_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_key: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    credential_handle: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_challenge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("uq_source_profiles_identity", "platform", "profile_key", unique=True),)


__all__ = [
    "DiscoveryQueryRow",
    "IngestJobEventRow",
    "IngestJobRow",
    "RightsAttestationRow",
    "SourceProfileRow",
]
