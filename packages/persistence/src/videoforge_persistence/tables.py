"""SQLAlchemy 2 声明式表。

约定（docs/implementation/50 §11）：
- 主键 UUIDv7/ULID 字符串；时间一律 timestamptz(UTC)；
- 核心过滤/唯一性字段用列，灵活结构才进 JSONB；
- 枚举存文本（校验在合同层），避免 PG 原生枚举的迁移成本；
- artifacts.sha256 建索引但**不唯一**：同哈希不同来源的记录不得合并（30 §7）。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    vertical: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_language: Mapped[str] = mapped_column(String(20), nullable=False)
    target_languages: Mapped[list] = mapped_column(JSONB, nullable=False)
    creation_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    execution_policy: Mapped[str] = mapped_column(String(40), nullable=False)
    trend_cluster_id: Mapped[str | None] = mapped_column(String(36))
    source_asset_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    channel_profile_id: Mapped[str | None] = mapped_column(String(36))
    template_version_id: Mapped[str | None] = mapped_column(String(36))
    workflow_id: Mapped[str | None] = mapped_column(String(200))
    budget_policy: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    phash: Mapped[str | None] = mapped_column(String(64))
    ahash: Mapped[str | None] = mapped_column(String(64))
    audio_fingerprint: Mapped[str | None] = mapped_column(Text)
    media: Mapped[dict | None] = mapped_column(JSONB)
    upstream_artifact_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    produced_by: Mapped[dict | None] = mapped_column(JSONB)
    storage: Mapped[dict] = mapped_column(JSONB, nullable=False)
    retention_policy: Mapped[str | None] = mapped_column(String(100))
    sensitivity: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_artifacts_sha256", "sha256"),)


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "ix_outbox_events_pending",
            "occurred_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )


class ProcessedEventRow(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    consumer: Mapped[str] = mapped_column(String(200), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrendItemSnapshotRow(Base):
    """周期采集的不可变观测（docs/modules/40 §3.1）。只增，热度靠序列算。"""

    __tablename__ = "trend_item_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    region: Mapped[str | None] = mapped_column(String(20))
    locale: Mapped[str | None] = mapped_column(String(20))
    item_id: Mapped[str] = mapped_column(String(200), nullable=False)
    author_id: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    views: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    saves: Mapped[int | None] = mapped_column(BigInteger)
    followers_at_observation: Mapped[int | None] = mapped_column(BigInteger)
    rank: Mapped[int | None] = mapped_column(Integer)
    hashtag_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sound_id: Mapped[str | None] = mapped_column(String(200))
    raw_artifact_id: Mapped[str | None] = mapped_column(String(36))
    collector_version: Mapped[str] = mapped_column(String(100), nullable=False)
    source_confidence: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (Index("ix_trend_snapshots_item", "platform", "item_id", "observed_at"),)


class TrendClusterRow(Base):
    """跨平台/跨语言同事件信号聚类（docs/architecture/31 §1.1）。可版本化聚合。"""

    __tablename__ = "trend_clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_topic: Mapped[str] = mapped_column(String(300), nullable=False)
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    entities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    member_item_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    snapshot_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sub_scores: Mapped[dict | None] = mapped_column(JSONB)
    hot_score: Mapped[float | None] = mapped_column(Float, index=True)
    weights_version: Mapped[str | None] = mapped_column(String(50))
    reason_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    embedding_ref: Mapped[str | None] = mapped_column(String(200))
    source_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    vertical: Mapped[str | None] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkerRow(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    hostname: Mapped[str] = mapped_column(String(200), nullable=False)
    os: Mapped[str] = mapped_column(String(50), nullable=False)
    arch: Mapped[str] = mapped_column(String(50), nullable=False)
    capabilities: Mapped[list] = mapped_column(JSONB, nullable=False)
    execution_location: Mapped[str] = mapped_column(String(20), nullable=False)
    toolchain: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkerTaskRow(Base):
    __tablename__ = "worker_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    capability: Mapped[str] = mapped_column(String(200), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    execution_policy: Mapped[str] = mapped_column(String(40), nullable=False)
    # status ∈ PENDING / LEASED / COMPLETED / FAILED（FAILED 为终态，不再可领）
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    # attempt = 已消耗尝试数（每次 claim +1）；达到 max_attempts 即转终态 FAILED
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    lease_id: Mapped[str | None] = mapped_column(String(36))
    leased_by: Mapped[str | None] = mapped_column(ForeignKey("workers.id"))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output: Mapped[dict | None] = mapped_column(JSONB)
    output_digest: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_worker_tasks_claim", "status", "created_at"),)
