"""M-W10 设置仓储：CAS、singleton 与 owner/credential 原子性。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, select

from videoforge_persistence import (
    CredentialEntryRecord,
    DuplicateError,
    PlatformAccountBindingRecord,
    ProviderConfigurationRecord,
    SettingsRepository,
    VaultMetadataRecord,
    VersionConflictError,
    new_id,
    session_scope,
)
from videoforge_persistence.settings_tables import CredentialEntryRow

T0 = datetime(2026, 7, 27, tzinfo=UTC)


def _vault() -> VaultMetadataRecord:
    return VaultMetadataRecord(
        id="local-v1",
        crypto_version=1,
        kdf_name="argon2id",
        kdf_parameters={
            "type": "ID",
            "version": 19,
            "time_cost": 3,
            "memory_cost": 65536,
            "parallelism": 4,
            "hash_length": 32,
        },
        salt=b"s" * 16,
        wrapped_key_nonce=b"n" * 16,
        wrapped_master_key=b"k" * 32,
        wrapped_key_tag=b"t" * 16,
        created_at=T0,
        updated_at=T0,
    )


def _provider(kind: str = "LLM") -> ProviderConfigurationRecord:
    return ProviderConfigurationRecord(
        kind=kind,
        provider_name="synthetic-provider",
        model_name="synthetic-model",
        base_url="https://example.invalid/v1",
        enabled=False,
        options={"temperature": 0.2},
        row_version=1,
        created_at=T0,
        updated_at=T0,
    )


def _account(account_id: str | None = None) -> PlatformAccountBindingRecord:
    return PlatformAccountBindingRecord(
        id=account_id or new_id(),
        platform="DOUYIN",
        display_name="合成账号",
        external_account_id="synthetic-account",
        auth_method="OFFICIAL_API",
        binding="SERVER_ENCRYPTED",
        locale="zh-CN",
        publishing_window=None,
        enabled=False,
        verification_status="UNVERIFIED",
        row_version=1,
        created_at=T0,
        updated_at=T0,
    )


def _server_credential(owner_type: str, owner_id: str) -> CredentialEntryRecord:
    return CredentialEntryRecord(
        id=new_id(),
        owner_type=owner_type,
        owner_id=owner_id,
        storage_kind="SERVER_ENCRYPTED",
        purpose="synthetic-test",
        external_handle=None,
        nonce=b"n" * 16,
        ciphertext=b"ciphertext-only",
        auth_tag=b"t" * 16,
        created_at=T0,
        updated_at=T0,
    )


def test_vault_singleton_roundtrip_and_duplicate_rollback(migrated_engine: Engine) -> None:
    with session_scope(migrated_engine) as session:
        stored = SettingsRepository(session).create_vault_metadata(_vault())
        assert stored.kdf_name == "argon2id"

    with session_scope(migrated_engine) as session:
        loaded = SettingsRepository(session).get_vault_metadata()
        assert loaded == _vault()

    with pytest.raises(DuplicateError):
        with session_scope(migrated_engine) as session:
            SettingsRepository(session).create_vault_metadata(_vault())

    with session_scope(migrated_engine) as session:
        assert SettingsRepository(session).get_vault_metadata() == _vault()


def test_provider_cas_and_delete_remove_owned_credential(migrated_engine: Engine) -> None:
    with session_scope(migrated_engine) as session:
        repo = SettingsRepository(session)
        provider = repo.create_provider(_provider())
        repo.replace_credential(_server_credential("PROVIDER", provider.kind))

    with session_scope(migrated_engine) as session:
        repo = SettingsRepository(session)
        provider = repo.get_provider("LLM")
        assert provider is not None
        updated = repo.update_provider(
            ProviderConfigurationRecord(
                **{**provider.__dict__, "model_name": "synthetic-model-v2"}
            ),
            expected_version=1,
        )
        assert updated.row_version == 2
        assert repo.get_credential("PROVIDER", "LLM") is not None

    with pytest.raises(VersionConflictError):
        with session_scope(migrated_engine) as session:
            repo = SettingsRepository(session)
            provider = repo.get_provider("LLM")
            assert provider is not None
            repo.update_provider(provider, expected_version=1)

    with session_scope(migrated_engine) as session:
        repo = SettingsRepository(session)
        repo.delete_provider("LLM", expected_version=2)

    with session_scope(migrated_engine) as session:
        repo = SettingsRepository(session)
        assert repo.get_provider("LLM") is None
        assert repo.get_credential("PROVIDER", "LLM") is None


def test_account_locator_unique_cas_and_atomic_delete(migrated_engine: Engine) -> None:
    account = _account()
    with session_scope(migrated_engine) as session:
        repo = SettingsRepository(session)
        repo.create_account(account)
        repo.replace_credential(_server_credential("ACCOUNT", account.id))

    duplicate = _account()
    with pytest.raises(DuplicateError):
        with session_scope(migrated_engine) as session:
            SettingsRepository(session).create_account(duplicate)

    with session_scope(migrated_engine) as session:
        repo = SettingsRepository(session)
        current = repo.get_account(account.id)
        assert current is not None
        updated = repo.update_account(
            PlatformAccountBindingRecord(
                **{**current.__dict__, "display_name": "合成账号二"}
            ),
            expected_version=1,
        )
        assert updated.row_version == 2
        assert updated.verification_status == "UNVERIFIED"

    with session_scope(migrated_engine) as session:
        repo = SettingsRepository(session)
        repo.delete_account(account.id, expected_version=2)
        assert repo.get_credential("ACCOUNT", account.id) is None


def test_desktop_locator_has_no_ciphertext(migrated_engine: Engine) -> None:
    account = _account()
    locator = CredentialEntryRecord(
        id=new_id(),
        owner_type="ACCOUNT",
        owner_id=account.id,
        storage_kind="DESKTOP",
        purpose="browser-session",
        external_handle="douyin-main-cookie",
        nonce=None,
        ciphertext=None,
        auth_tag=None,
        created_at=T0,
        updated_at=T0,
    )
    with session_scope(migrated_engine) as session:
        repo = SettingsRepository(session)
        repo.create_account(account)
        repo.replace_credential(locator)

    with session_scope(migrated_engine) as session:
        row = session.scalars(
            select(CredentialEntryRow).where(CredentialEntryRow.owner_id == account.id)
        ).one()
        assert row.external_handle == "douyin-main-cookie"
        assert row.nonce is row.ciphertext is row.auth_tag is None
