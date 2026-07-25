"""source_assets 与分析链（analysis_runs / analysis_artifacts）

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("content_id", sa.String(300)),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(30), nullable=False),
        sa.Column("file_sha256", sa.String(64)),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_assets_platform", "source_assets", ["platform"])
    op.create_index("ix_source_assets_disposition", "source_assets", ["disposition"])
    op.create_index("ix_source_assets_created_at", "source_assets", ["created_at"])
    op.create_index("ix_source_assets_file_sha256", "source_assets", ["file_sha256"])
    # 部分唯一：平台内容 ID 都在时防重复导入；手工导入（content_id 是文件名）排除在外
    op.create_index(
        "uq_source_assets_platform_content",
        "source_assets",
        ["platform", "content_id"],
        unique=True,
        postgresql_where=sa.text("content_id IS NOT NULL AND platform <> 'manual'"),
    )
    # 短链 / 不可解析输入没有 content_id，其幂等身份是 sha256(original_input)
    op.create_index(
        "uq_source_assets_input_digest",
        "source_assets",
        ["input_digest"],
        unique=True,
        postgresql_where=sa.text("content_id IS NULL"),
    )
    # 手工导入的身份就是文件哈希（content_id 是文件名，不可靠）。**只对 manual 唯一**——
    # 不同平台的 URL 资产共享同一 file_sha256 是「FILE 层重复组」的设计前提，不能全局唯一。
    op.create_index(
        "uq_source_assets_manual_file_sha256",
        "source_assets",
        ["file_sha256"],
        unique=True,
        postgresql_where=sa.text("platform = 'manual' AND file_sha256 IS NOT NULL"),
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("source_asset_id", sa.String(36), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stages", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analysis_runs_project_id", "analysis_runs", ["project_id"])
    op.create_index(
        "ix_analysis_runs_project_created", "analysis_runs", ["project_id", "created_at"]
    )

    op.create_table(
        "analysis_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("tool_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analysis_artifacts_project_id", "analysis_artifacts", ["project_id"])
    op.create_index(
        "uq_analysis_artifacts_kind_cache",
        "analysis_artifacts",
        ["kind", "cache_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("analysis_artifacts")
    op.drop_table("analysis_runs")
    op.drop_table("source_assets")
