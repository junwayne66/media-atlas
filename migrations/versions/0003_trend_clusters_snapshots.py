"""VF-104：trend_item_snapshots 与 trend_clusters（M01 热点情报）

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trend_item_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("region", sa.String(20)),
        sa.Column("locale", sa.String(20)),
        sa.Column("item_id", sa.String(200), nullable=False),
        sa.Column("author_id", sa.String(200)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("views", sa.BigInteger()),
        sa.Column("likes", sa.BigInteger()),
        sa.Column("comments", sa.BigInteger()),
        sa.Column("shares", sa.BigInteger()),
        sa.Column("saves", sa.BigInteger()),
        sa.Column("followers_at_observation", sa.BigInteger()),
        sa.Column("rank", sa.Integer()),
        sa.Column("hashtag_ids", JSONB, nullable=False),
        sa.Column("sound_id", sa.String(200)),
        sa.Column("raw_artifact_id", sa.String(36)),
        sa.Column("collector_version", sa.String(100), nullable=False),
        sa.Column("source_confidence", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_trend_snapshots_item", "trend_item_snapshots", ["platform", "item_id", "observed_at"]
    )

    op.create_table(
        "trend_clusters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("canonical_topic", sa.String(300), nullable=False),
        sa.Column("keywords", JSONB, nullable=False),
        sa.Column("entities", JSONB, nullable=False),
        sa.Column("member_item_ids", JSONB, nullable=False),
        sa.Column("snapshot_ids", JSONB, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("sub_scores", JSONB),
        sa.Column("hot_score", sa.Float()),
        sa.Column("weights_version", sa.String(50)),
        sa.Column("reason_codes", JSONB, nullable=False),
        sa.Column("embedding_ref", sa.String(200)),
        sa.Column("source_confidence", sa.Float(), nullable=False),
        sa.Column("vertical", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trend_clusters_stage", "trend_clusters", ["stage"])
    op.create_index("ix_trend_clusters_hot_score", "trend_clusters", ["hot_score"])
    op.create_index("ix_trend_clusters_vertical", "trend_clusters", ["vertical"])


def downgrade() -> None:
    op.drop_table("trend_clusters")
    op.drop_table("trend_item_snapshots")
