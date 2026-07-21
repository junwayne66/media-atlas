"""VF-003：projects、artifacts、outbox_events、processed_events 初版

Revision ID: 0001
Revises:
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("vertical", sa.String(100), nullable=False),
        sa.Column("source_language", sa.String(20), nullable=False),
        sa.Column("target_languages", JSONB, nullable=False),
        sa.Column("creation_mode", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("execution_policy", sa.String(40), nullable=False),
        sa.Column("trend_cluster_id", sa.String(36)),
        sa.Column("source_asset_ids", JSONB, nullable=False),
        sa.Column("channel_profile_id", sa.String(36)),
        sa.Column("template_version_id", sa.String(36)),
        sa.Column("workflow_id", sa.String(200)),
        sa.Column("budget_policy", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_vertical", "projects", ["vertical"])
    op.create_index("ix_projects_status", "projects", ["status"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id")),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("phash", sa.String(64)),
        sa.Column("ahash", sa.String(64)),
        sa.Column("audio_fingerprint", sa.Text()),
        sa.Column("media", JSONB),
        sa.Column("upstream_artifact_ids", JSONB, nullable=False),
        sa.Column("produced_by", JSONB),
        sa.Column("storage", JSONB, nullable=False),
        sa.Column("retention_policy", sa.String(100)),
        sa.Column("sensitivity", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])
    # 同哈希不同来源不得合并（30 §7），因此只建普通索引，不加唯一约束
    op.create_index("ix_artifacts_sha256", "artifacts", ["sha256"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["occurred_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("consumer", sa.String(200), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_table("outbox_events")
    op.drop_table("artifacts")
    op.drop_table("projects")
