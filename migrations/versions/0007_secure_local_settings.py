"""本地安全设置、加密凭据库与平台账号 locator（M-W10）。

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credential_vault_metadata",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("crypto_version", sa.Integer(), nullable=False),
        sa.Column("kdf_name", sa.String(32), nullable=False),
        sa.Column("kdf_parameters", JSONB, nullable=False),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_key_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_master_key", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_key_tag", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "credential_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_type", sa.String(20), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("storage_kind", sa.String(30), nullable=False),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("external_handle", sa.Text()),
        sa.Column("nonce", sa.LargeBinary()),
        sa.Column("ciphertext", sa.LargeBinary()),
        sa.Column("auth_tag", sa.LargeBinary()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            """
            (
              storage_kind = 'SERVER_ENCRYPTED'
              AND external_handle IS NULL
              AND nonce IS NOT NULL
              AND ciphertext IS NOT NULL
              AND auth_tag IS NOT NULL
            )
            OR
            (
              storage_kind IN ('DESKTOP', 'DEVICE')
              AND external_handle IS NOT NULL
              AND nonce IS NULL
              AND ciphertext IS NULL
              AND auth_tag IS NULL
            )
            """,
            name="ck_credential_entries_storage_shape",
        ),
    )
    op.create_index(
        "uq_credential_entries_owner",
        "credential_entries",
        ["owner_type", "owner_id"],
        unique=True,
    )

    op.create_table(
        "provider_configurations",
        sa.Column("kind", sa.String(30), primary_key=True),
        sa.Column("provider_name", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(200)),
        sa.Column("base_url", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("options", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "platform_account_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("external_account_id", sa.String(200), nullable=False),
        sa.Column("auth_method", sa.String(30), nullable=False),
        sa.Column("binding", sa.String(30), nullable=False),
        sa.Column("locale", sa.String(20), nullable=False),
        sa.Column("publishing_window", sa.String(200)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "verification_status",
            sa.String(20),
            nullable=False,
            server_default="UNVERIFIED",
        ),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_platform_account_bindings_identity",
        "platform_account_bindings",
        ["platform", "external_account_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("platform_account_bindings")
    op.drop_table("provider_configurations")
    op.drop_table("credential_entries")
    op.drop_table("credential_vault_metadata")
