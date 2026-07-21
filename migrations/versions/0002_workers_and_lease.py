"""VF-007：workers 与 worker_tasks（Task Lease 协议，30 §5）

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("hostname", sa.String(200), nullable=False),
        sa.Column("os", sa.String(50), nullable=False),
        sa.Column("arch", sa.String(50), nullable=False),
        sa.Column("capabilities", JSONB, nullable=False),
        sa.Column("execution_location", sa.String(20), nullable=False),
        sa.Column("toolchain", JSONB, nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "worker_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("capability", sa.String(200), nullable=False),
        sa.Column("params", JSONB, nullable=False),
        sa.Column("execution_policy", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("lease_id", sa.String(36)),
        sa.Column("leased_by", sa.String(36), sa.ForeignKey("workers.id")),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("output", JSONB),
        sa.Column("output_digest", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_worker_tasks_claim", "worker_tasks", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("worker_tasks")
    op.drop_table("workers")
