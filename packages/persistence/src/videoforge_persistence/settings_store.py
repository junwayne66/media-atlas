"""M-W10 安全设置仓储。

只处理非敏感配置、外部 locator 和已经加密的字节；明文 Secret/KDF/AEAD 均属于 API 应用层。
所有方法依赖调用方提供的 Session，不自行 commit，保证 owner + credential 在同一事务内更新。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from videoforge_persistence.errors import DuplicateError, NotFoundError, VersionConflictError
from videoforge_persistence.settings_tables import (
    CredentialEntryRow,
    PlatformAccountBindingRow,
    ProviderConfigurationRow,
    VaultMetadataRow,
)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class VaultMetadataRecord:
    id: str
    crypto_version: int
    kdf_name: str
    kdf_parameters: dict[str, Any]
    salt: bytes
    wrapped_key_nonce: bytes
    wrapped_master_key: bytes
    wrapped_key_tag: bytes
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CredentialEntryRecord:
    id: str
    owner_type: str
    owner_id: str
    storage_kind: str
    purpose: str
    external_handle: str | None
    nonce: bytes | None
    ciphertext: bytes | None
    auth_tag: bytes | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProviderConfigurationRecord:
    kind: str
    provider_name: str
    model_name: str | None
    base_url: str | None
    enabled: bool
    options: dict[str, Any]
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PlatformAccountBindingRecord:
    id: str
    platform: str
    display_name: str
    external_account_id: str
    auth_method: str
    binding: str
    locale: str
    publishing_window: str | None
    enabled: bool
    verification_status: str
    row_version: int
    created_at: datetime
    updated_at: datetime


def _vault_record(row: VaultMetadataRow) -> VaultMetadataRecord:
    return VaultMetadataRecord(
        id=row.id,
        crypto_version=row.crypto_version,
        kdf_name=row.kdf_name,
        kdf_parameters=dict(row.kdf_parameters),
        salt=bytes(row.salt),
        wrapped_key_nonce=bytes(row.wrapped_key_nonce),
        wrapped_master_key=bytes(row.wrapped_master_key),
        wrapped_key_tag=bytes(row.wrapped_key_tag),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _credential_record(row: CredentialEntryRow) -> CredentialEntryRecord:
    return CredentialEntryRecord(
        id=row.id,
        owner_type=row.owner_type,
        owner_id=row.owner_id,
        storage_kind=row.storage_kind,
        purpose=row.purpose,
        external_handle=row.external_handle,
        nonce=None if row.nonce is None else bytes(row.nonce),
        ciphertext=None if row.ciphertext is None else bytes(row.ciphertext),
        auth_tag=None if row.auth_tag is None else bytes(row.auth_tag),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _provider_record(row: ProviderConfigurationRow) -> ProviderConfigurationRecord:
    return ProviderConfigurationRecord(
        kind=row.kind,
        provider_name=row.provider_name,
        model_name=row.model_name,
        base_url=row.base_url,
        enabled=row.enabled,
        options=dict(row.options),
        row_version=row.row_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _account_record(row: PlatformAccountBindingRow) -> PlatformAccountBindingRecord:
    return PlatformAccountBindingRecord(
        id=row.id,
        platform=row.platform,
        display_name=row.display_name,
        external_account_id=row.external_account_id,
        auth_method=row.auth_method,
        binding=row.binding,
        locale=row.locale,
        publishing_window=row.publishing_window,
        enabled=row.enabled,
        verification_status=row.verification_status,
        row_version=row.row_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SettingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # Vault singleton

    def get_vault_metadata(self) -> VaultMetadataRecord | None:
        row = self._session.get(VaultMetadataRow, "local-v1")
        return None if row is None else _vault_record(row)

    def create_vault_metadata(self, record: VaultMetadataRecord) -> VaultMetadataRecord:
        row = VaultMetadataRow(**record.__dict__)
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError("credential vault 已初始化") from exc
        return _vault_record(row)

    # Credential entries

    def get_credential(self, owner_type: str, owner_id: str) -> CredentialEntryRecord | None:
        stmt = select(CredentialEntryRow).where(
            CredentialEntryRow.owner_type == owner_type,
            CredentialEntryRow.owner_id == owner_id,
        )
        row = self._session.scalars(stmt).first()
        return None if row is None else _credential_record(row)

    def replace_credential(self, record: CredentialEntryRecord) -> CredentialEntryRecord:
        self.clear_credential(record.owner_type, record.owner_id)
        row = CredentialEntryRow(**record.__dict__)
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(
                f"credential owner 已存在: {record.owner_type}/{record.owner_id}"
            ) from exc
        return _credential_record(row)

    def clear_credential(self, owner_type: str, owner_id: str) -> bool:
        stmt = (
            delete(CredentialEntryRow)
            .where(
                CredentialEntryRow.owner_type == owner_type,
                CredentialEntryRow.owner_id == owner_id,
            )
            .returning(CredentialEntryRow.id)
        )
        return self._session.execute(stmt).scalar_one_or_none() is not None

    # Provider configurations

    def list_providers(self) -> list[ProviderConfigurationRecord]:
        stmt = select(ProviderConfigurationRow).order_by(ProviderConfigurationRow.kind)
        return [_provider_record(row) for row in self._session.scalars(stmt)]

    def get_provider(self, kind: str) -> ProviderConfigurationRecord | None:
        row = self._session.get(ProviderConfigurationRow, kind)
        return None if row is None else _provider_record(row)

    def create_provider(
        self, record: ProviderConfigurationRecord
    ) -> ProviderConfigurationRecord:
        row = ProviderConfigurationRow(**record.__dict__)
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(f"provider 配置已存在: {record.kind}") from exc
        return _provider_record(row)

    def update_provider(
        self,
        record: ProviderConfigurationRecord,
        *,
        expected_version: int,
    ) -> ProviderConfigurationRecord:
        now = _now()
        values = {
            "provider_name": record.provider_name,
            "model_name": record.model_name,
            "base_url": record.base_url,
            "enabled": record.enabled,
            "options": record.options,
            "row_version": expected_version + 1,
            "updated_at": now,
        }
        stmt = (
            update(ProviderConfigurationRow)
            .where(
                ProviderConfigurationRow.kind == record.kind,
                ProviderConfigurationRow.row_version == expected_version,
            )
            .values(**values)
            .returning(ProviderConfigurationRow.kind)
        )
        if self._session.execute(stmt).scalar_one_or_none() is None:
            if self._session.get(ProviderConfigurationRow, record.kind) is None:
                raise NotFoundError("provider_configuration", record.kind)
            raise VersionConflictError("provider_configuration", record.kind, expected_version)
        return replace(record, row_version=expected_version + 1, updated_at=now)

    def delete_provider(self, kind: str, *, expected_version: int) -> None:
        stmt = (
            delete(ProviderConfigurationRow)
            .where(
                ProviderConfigurationRow.kind == kind,
                ProviderConfigurationRow.row_version == expected_version,
            )
            .returning(ProviderConfigurationRow.kind)
        )
        if self._session.execute(stmt).scalar_one_or_none() is None:
            if self._session.get(ProviderConfigurationRow, kind) is None:
                raise NotFoundError("provider_configuration", kind)
            raise VersionConflictError("provider_configuration", kind, expected_version)
        self.clear_credential("PROVIDER", kind)

    # Platform account bindings

    def list_accounts(self) -> list[PlatformAccountBindingRecord]:
        stmt = select(PlatformAccountBindingRow).order_by(
            PlatformAccountBindingRow.platform,
            PlatformAccountBindingRow.display_name,
            PlatformAccountBindingRow.id,
        )
        return [_account_record(row) for row in self._session.scalars(stmt)]

    def get_account(self, account_id: str) -> PlatformAccountBindingRecord | None:
        row = self._session.get(PlatformAccountBindingRow, account_id)
        return None if row is None else _account_record(row)

    def create_account(
        self, record: PlatformAccountBindingRecord
    ) -> PlatformAccountBindingRecord:
        row = PlatformAccountBindingRow(**record.__dict__)
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicateError(
                f"platform account 已存在: {record.platform}/{record.external_account_id}"
            ) from exc
        return _account_record(row)

    def update_account(
        self,
        record: PlatformAccountBindingRecord,
        *,
        expected_version: int,
    ) -> PlatformAccountBindingRecord:
        now = _now()
        values = {
            "platform": record.platform,
            "display_name": record.display_name,
            "external_account_id": record.external_account_id,
            "auth_method": record.auth_method,
            "binding": record.binding,
            "locale": record.locale,
            "publishing_window": record.publishing_window,
            "enabled": record.enabled,
            # 本任务绝不执行在线验证，写回时强制保持 UNVERIFIED。
            "verification_status": "UNVERIFIED",
            "row_version": expected_version + 1,
            "updated_at": now,
        }
        stmt = (
            update(PlatformAccountBindingRow)
            .where(
                PlatformAccountBindingRow.id == record.id,
                PlatformAccountBindingRow.row_version == expected_version,
            )
            .values(**values)
            .returning(PlatformAccountBindingRow.id)
        )
        try:
            hit = self._session.execute(stmt).scalar_one_or_none()
        except IntegrityError as exc:
            raise DuplicateError(
                f"platform account 已存在: {record.platform}/{record.external_account_id}"
            ) from exc
        if hit is None:
            if self._session.get(PlatformAccountBindingRow, record.id) is None:
                raise NotFoundError("platform_account_binding", record.id)
            raise VersionConflictError(
                "platform_account_binding", record.id, expected_version
            )
        return replace(
            record,
            verification_status="UNVERIFIED",
            row_version=expected_version + 1,
            updated_at=now,
        )

    def delete_account(self, account_id: str, *, expected_version: int) -> None:
        stmt = (
            delete(PlatformAccountBindingRow)
            .where(
                PlatformAccountBindingRow.id == account_id,
                PlatformAccountBindingRow.row_version == expected_version,
            )
            .returning(PlatformAccountBindingRow.id)
        )
        if self._session.execute(stmt).scalar_one_or_none() is None:
            if self._session.get(PlatformAccountBindingRow, account_id) is None:
                raise NotFoundError("platform_account_binding", account_id)
            raise VersionConflictError(
                "platform_account_binding", account_id, expected_version
            )
        self.clear_credential("ACCOUNT", account_id)


__all__ = [
    "CredentialEntryRecord",
    "PlatformAccountBindingRecord",
    "ProviderConfigurationRecord",
    "SettingsRepository",
    "VaultMetadataRecord",
]
