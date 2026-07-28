"""M-W10 本地安全设置的 SQLAlchemy 表。

本层只保存非敏感元数据、外部安全存储 locator 与认证密文；不会接触任何明文 Secret。
枚举继续存文本，校验由应用合同层完成。
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from videoforge_persistence.tables import Base


class VaultMetadataRow(Base):
    """本地凭据库单例：口令只用于解封 wrapped master key，本身不落库。"""

    __tablename__ = "credential_vault_metadata"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    crypto_version: Mapped[int] = mapped_column(Integer, nullable=False)
    kdf_name: Mapped[str] = mapped_column(String(32), nullable=False)
    kdf_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    salt: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrapped_key_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrapped_master_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrapped_key_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CredentialEntryRow(Base):
    """一个 owner 的服务端密文，或 Desktop/Device 外部 locator。

    CHECK 保证两种形态互斥：SERVER_ENCRYPTED 必须有完整 AEAD 三元组；DESKTOP/DEVICE
    只能有不透明 handle，避免 Web 控制面误收 Cookie/设备会话明文。
    """

    __tablename__ = "credential_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    storage_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    external_handle: Mapped[str | None] = mapped_column(Text)
    nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    auth_tag: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("uq_credential_entries_owner", "owner_type", "owner_id", unique=True),
        CheckConstraint(
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


class ProviderConfigurationRow(Base):
    __tablename__ = "provider_configurations"

    kind: Mapped[str] = mapped_column(String(30), primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(200))
    base_url: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlatformAccountBindingRow(Base):
    __tablename__ = "platform_account_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(30), nullable=False)
    binding: Mapped[str] = mapped_column(String(30), nullable=False)
    locale: Mapped[str] = mapped_column(String(20), nullable=False)
    publishing_window: Mapped[str | None] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNVERIFIED"
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "uq_platform_account_bindings_identity",
            "platform",
            "external_account_id",
            unique=True,
        ),
    )


__all__ = [
    "CredentialEntryRow",
    "PlatformAccountBindingRow",
    "ProviderConfigurationRow",
    "VaultMetadataRow",
]
