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


class SourceAssetRow(Base):
    """来源素材聚合（VF-105/107 持久化面）。

    列只放过滤/唯一性所需字段，完整合同进 payload JSONB（合同演进不必每次改列）。
    (platform, content_id) 部分唯一：二者都非空时防重复导入；platform='manual' 排除在外
    ——手工导入的 content_id 是文件名，同名不同文件是常态，其去重靠 file_sha256。
    input_digest = sha256(original_input)：短链 / 不可解析输入没有 content_id，
    其幂等身份只能是原始输入本身；用摘要而非原文入索引（原文可能很长，不适合直接进 btree）。
    该唯一索引只覆盖 content_id IS NULL 的行，可解析素材仍按 (platform, content_id) 去重。
    """

    __tablename__ = "source_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content_id: Mapped[str | None] = mapped_column(String(300))
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_source_assets_created_at", "created_at"),
        Index("ix_source_assets_file_sha256", "file_sha256"),
        Index(
            "uq_source_assets_platform_content",
            "platform",
            "content_id",
            unique=True,
            postgresql_where=text("content_id IS NOT NULL AND platform <> 'manual'"),
        ),
        Index(
            "uq_source_assets_input_digest",
            "input_digest",
            unique=True,
            postgresql_where=text("content_id IS NULL"),
        ),
        # 手工导入的身份是文件哈希；只对 platform='manual' 唯一——不同平台的 URL 资产
        # 共享同一 file_sha256 是「FILE 层重复组」的设计前提，绝不能做成全局唯一。
        Index(
            "uq_source_assets_manual_file_sha256",
            "file_sha256",
            unique=True,
            postgresql_where=text("platform = 'manual' AND file_sha256 IS NOT NULL"),
        ),
    )


class AnalysisRunRow(Base):
    """一次分析链执行（ASR→OCR→VLM→Blueprint）。stages 逐阶段记录缓存命中与产物。"""

    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False)
    # status ∈ RUNNING / COMPLETED / FAILED
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    stages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_analysis_runs_project_created", "project_id", "created_at"),)


class AnalysisArtifactRow(Base):
    """分析产物（Transcript / TextTrackSet / VisualAnalysis / VideoBlueprint）。

    (kind, cache_key) 唯一 —— 缓存命中即按此二元组查到就复用，不再调 Provider（41 §11）。
    project_id 记录**首个**创建该产物的项目；产物按 (kind, cache_key) 跨项目复用，
    因此它不表示归属关系（某项目实际用了哪些产物，看 analysis_runs.stages[].artifact_id）。
    """

    __tablename__ = "analysis_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("uq_analysis_artifacts_kind_cache", "kind", "cache_key", unique=True),)


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
