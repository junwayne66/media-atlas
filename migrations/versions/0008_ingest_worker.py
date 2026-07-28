"""VF-108 可恢复采集 Worker。

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_queries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("query_text", sa.String(200), nullable=False),
        sa.Column("filters", JSONB, nullable=False),
        sa.Column("max_items", sa.Integer(), nullable=False),
        sa.Column("max_scrolls", sa.Integer(), nullable=False),
        sa.Column("idle_rounds", sa.Integer(), nullable=False),
        sa.Column("time_budget_s", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.String(36)),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("job_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("workflow_id", sa.String(200), unique=True),
        sa.Column("worker_task_id", sa.String(36)),
        sa.Column("source_asset_id", sa.String(36)),
        sa.Column("discovery_query_id", sa.String(36), sa.ForeignKey("discovery_queries.id")),
        sa.Column("profile_id", sa.String(36)),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("result", JSONB),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ingest_jobs_status", "ingest_jobs", ["status"])
    op.create_index("ix_ingest_jobs_created", "ingest_jobs", ["created_at", "id"])
    op.create_table(
        "ingest_job_events",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column(
            "job_id",
            sa.String(36),
            sa.ForeignKey("ingest_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30)),
        sa.Column("actor_id", sa.String(200)),
        sa.Column("message", sa.Text()),
        sa.Column("details", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ingest_job_events_timeline",
        "ingest_job_events",
        ["job_id", "created_at", "id"],
    )
    op.create_table(
        "rights_attestations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column(
            "source_asset_id", sa.String(36), sa.ForeignKey("source_assets.id"), nullable=False
        ),
        sa.Column("basis", sa.String(30), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_rights_attestations_source_asset_id",
        "rights_attestations",
        ["source_asset_id"],
    )
    op.create_table(
        "source_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("profile_key", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("credential_handle", sa.String(128)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_challenge_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_source_profiles_identity",
        "source_profiles",
        ["platform", "profile_key"],
        unique=True,
    )

    op.add_column("worker_tasks", sa.Column("workflow_id", sa.String(200)))
    op.add_column(
        "worker_tasks",
        sa.Column(
            "input_artifact_ids", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.add_column("worker_tasks", sa.Column("output_schema_ref", sa.Text()))
    op.add_column("worker_tasks", sa.Column("resource_limits", JSONB))
    op.add_column(
        "worker_tasks",
        sa.Column(
            "credential_handles", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.add_column(
        "worker_tasks", sa.Column("priority", sa.Integer(), nullable=False, server_default="0")
    )
    op.drop_index("ix_worker_tasks_claim", table_name="worker_tasks")
    op.create_index(
        "ix_worker_tasks_claim",
        "worker_tasks",
        ["status", "priority", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_worker_tasks_claim", table_name="worker_tasks")
    op.create_index("ix_worker_tasks_claim", "worker_tasks", ["status", "created_at"])
    op.drop_column("worker_tasks", "priority")
    op.drop_column("worker_tasks", "credential_handles")
    op.drop_column("worker_tasks", "resource_limits")
    op.drop_column("worker_tasks", "output_schema_ref")
    op.drop_column("worker_tasks", "input_artifact_ids")
    op.drop_column("worker_tasks", "workflow_id")
    op.drop_table("source_profiles")
    op.drop_table("rights_attestations")
    op.drop_table("ingest_job_events")
    op.drop_table("ingest_jobs")
    op.drop_table("discovery_queries")
