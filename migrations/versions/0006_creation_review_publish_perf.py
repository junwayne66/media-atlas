"""创作产物 / 审核决定 / 发布任务 / 表现快照（P3–P6 组装层落库）

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("doc_version", sa.Integer(), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("cache_key", sa.String(64)),
        # 护栏结论随产物一起存：脚本护栏不过仍落库（needs_review + issues），GET 要看得见。
        sa.Column("status", sa.Text()),
        sa.Column("issues", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_creative_documents_project_id", "creative_documents", ["project_id"])
    op.create_index(
        "uq_creative_documents_project_kind_version",
        "creative_documents",
        ["project_id", "kind", "doc_version"],
        unique=True,
    )

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("entity_version", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_decisions_entity_id", "review_decisions", ["entity_id"])

    op.create_table(
        "publish_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("account_id", sa.String(200), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        # payload 整存整取完整 PublishJob（**含 attempts**）——重建 Job 绝不剥离 attempts，
        # 否则 external_post_token 这道 durable latch 失效、恢复回路可二次发布（VF-503 警告）。
        sa.Column("payload", JSONB, nullable=False),
        # 发布元数据（PublishMetadata）：合同 PublishJob 只存 metadata_digest，
        # 效果归因（VF-602 features）需要语言等原文字段，故单列旁存。
        sa.Column("publish_metadata", JSONB),
        # 最近一次预检的输入探针与报告：submit 要在放行前用**同一能力源**重跑预检，
        # 因此探针必须持久化（预检不是一次性通行证）。
        sa.Column("media_probe", JSONB),
        sa.Column("preflight_report", JSONB),
        sa.Column("render_manifest_id", sa.String(36)),
        # 乐观锁令牌（纯存储关注点，不进合同）：并发迁移冲突 → 409。
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publish_jobs_state", "publish_jobs", ["state"])
    op.create_index("ix_publish_jobs_account", "publish_jobs", ["account_id", "platform"])
    op.create_index("ix_publish_jobs_external_post", "publish_jobs", ["platform", "state"])

    op.create_table(
        "performance_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(200), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("post_id", sa.String(200), nullable=False),
        sa.Column("age_hours", sa.Float(), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_performance_snapshots_post_id", "performance_snapshots", ["post_id"])
    op.create_index(
        "ix_performance_snapshots_account",
        "performance_snapshots",
        ["account_id", "platform"],
    )
    # 同 (帖子, 年龄点) 只保留一张快照——重复采集幂等返回既有，绝不写第二条。
    op.create_index(
        "uq_performance_snapshots_post_age",
        "performance_snapshots",
        ["post_id", "age_hours"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("performance_snapshots")
    op.drop_table("publish_jobs")
    op.drop_table("review_decisions")
    op.drop_table("creative_documents")
