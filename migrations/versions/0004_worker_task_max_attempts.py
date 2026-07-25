"""worker_tasks 尝试上限与终态 FAILED（P0 遗留：队列不再被永久失败任务空转）

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

DEFAULT_MAX_ATTEMPTS = 5


def upgrade() -> None:
    # 存量行按默认上限补齐后再收紧为 NOT NULL
    op.add_column(
        "worker_tasks",
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default=str(DEFAULT_MAX_ATTEMPTS),
        ),
    )
    op.alter_column("worker_tasks", "max_attempts", server_default=None)


def downgrade() -> None:
    # 终态 FAILED 无独立列（写在 status 里）；回滚时把它们放回 PENDING 免得卡死队列
    op.execute("UPDATE worker_tasks SET status = 'PENDING' WHERE status = 'FAILED'")
    op.drop_column("worker_tasks", "max_attempts")
