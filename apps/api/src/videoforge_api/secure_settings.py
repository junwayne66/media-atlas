"""M-W10 本地安全设置 API。

只保存配置与本地绑定材料，绝不发起 Provider/平台网络调用。账号始终 UNVERIFIED。
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Protocol
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy import Engine

from videoforge_api.credential_vault import (
    CredentialVault,
    InvalidPassphraseError,
    VaultBusyError,
    VaultEnvelope,
    VaultLockedError,
)
from videoforge_persistence import (
    CredentialEntryRecord,
    DuplicateError,
    NotFoundError,
    PlatformAccountBindingRecord,
    ProviderConfigurationRecord,
    SettingsRepository,
    VaultMetadataRecord,
    VersionConflictError,
    new_id,
    session_scope,
)

_VAULT_ID = "local-v1"
_SENSITIVE_OPTION_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "accesstoken",
    "authorization",
    "client_secret",
    "clientsecret",
    "cookie",
    "credential",
    "credentials",
    "password",
    "refresh_token",
    "refreshtoken",
    "secret",
}
_HANDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VaultState(StrEnum):
    UNINITIALIZED = "UNINITIALIZED"
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"


class ProviderKind(StrEnum):
    LLM = "LLM"
    ASR = "ASR"
    VLM = "VLM"


class CredentialAction(StrEnum):
    KEEP = "KEEP"
    REPLACE = "REPLACE"
    CLEAR = "CLEAR"


class Platform(StrEnum):
    DOUYIN = "DOUYIN"
    TIKTOK = "TIKTOK"


class AccountAuthMethod(StrEnum):
    OFFICIAL_API = "OFFICIAL_API"
    BROWSER_AUTOMATION = "BROWSER_AUTOMATION"
    ANDROID_DEVICE = "ANDROID_DEVICE"
    MANUAL_EXPORT = "MANUAL_EXPORT"


class AccountBinding(StrEnum):
    SERVER_ENCRYPTED = "SERVER_ENCRYPTED"
    DESKTOP = "DESKTOP"
    DEVICE = "DEVICE"


class SecretBundle(StrictRequest):
    api_key: SecretStr | None = Field(default=None, max_length=16384)
    access_token: SecretStr | None = Field(default=None, max_length=16384)
    refresh_token: SecretStr | None = Field(default=None, max_length=16384)
    client_secret: SecretStr | None = Field(default=None, max_length=16384)

    def has_value(self) -> bool:
        return any(
            value is not None and bool(value.get_secret_value())
            for value in (
                self.api_key,
                self.access_token,
                self.refresh_token,
                self.client_secret,
            )
        )

    def plaintext_json(self) -> bytes:
        values = {
            key: value.get_secret_value()
            for key, value in (
                ("api_key", self.api_key),
                ("access_token", self.access_token),
                ("refresh_token", self.refresh_token),
                ("client_secret", self.client_secret),
            )
            if value is not None and value.get_secret_value()
        }
        return json.dumps(
            values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class InitializeVaultRequest(StrictRequest):
    passphrase: SecretStr = Field(min_length=12, max_length=1024)
    confirmation: SecretStr = Field(min_length=12, max_length=1024)

    @model_validator(mode="after")
    def confirmations_match(self) -> InitializeVaultRequest:
        if self.passphrase.get_secret_value() != self.confirmation.get_secret_value():
            raise ValueError("口令确认不一致")
        return self


class UnlockVaultRequest(StrictRequest):
    passphrase: SecretStr = Field(min_length=1, max_length=1024)


class ProviderWriteRequest(StrictRequest):
    provider_name: str = Field(min_length=1, max_length=100)
    model_name: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=2048)
    enabled: bool = False
    options: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = Field(default=None, ge=1)
    credential_action: CredentialAction = CredentialAction.KEEP
    credential: SecretBundle | None = None

    @field_validator("provider_name", "model_name", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("服务地址格式无效")
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("服务地址必须是 http/https URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("服务地址不能包含凭据、查询参数或 fragment")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("远端服务地址必须使用 HTTPS")
        return normalized

    @field_validator("options")
    @classmethod
    def options_must_be_nonsecret(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 32768:
            raise ValueError("非敏感选项超过 32 KiB")

        def visit(node: Any) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
                    if normalized in _SENSITIVE_OPTION_KEYS:
                        raise ValueError("非敏感选项中包含受保护字段；请使用凭据输入")
                    visit(child)
            elif isinstance(node, list):
                for child in node:
                    visit(child)

        visit(value)
        return value

    @model_validator(mode="after")
    def credential_action_shape(self) -> ProviderWriteRequest:
        has_secret = self.credential is not None and self.credential.has_value()
        if self.credential_action is CredentialAction.REPLACE and not has_secret:
            raise ValueError("替换凭据时必须提供凭据值")
        if self.credential_action is not CredentialAction.REPLACE and self.credential is not None:
            raise ValueError("只有替换凭据时才能提交凭据值")
        return self


class AccountWriteRequest(StrictRequest):
    platform: Platform
    display_name: str = Field(min_length=1, max_length=200)
    external_account_id: str = Field(min_length=1, max_length=200)
    auth_method: AccountAuthMethod
    binding: AccountBinding
    locale: str = Field(min_length=2, max_length=20)
    publishing_window: str | None = Field(default=None, max_length=200)
    enabled: bool = False
    expected_version: int | None = Field(default=None, ge=1)
    credential_action: CredentialAction = CredentialAction.KEEP
    credential: SecretBundle | None = None
    external_credential_ref: str | None = Field(default=None, min_length=8, max_length=200)

    @field_validator(
        "display_name",
        "external_account_id",
        "locale",
        "publishing_window",
        mode="before",
    )
    @classmethod
    def trim_account_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("external_credential_ref")
    @classmethod
    def validate_opaque_handle(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HANDLE_RE.fullmatch(value):
            raise ValueError("外部凭据引用必须是不透明 handle")
        lowered = value.lower()
        if lowered.startswith("eyj") or "bearer" in lowered or "password=" in lowered:
            raise ValueError("外部凭据引用疑似明文凭据")
        return value

    @model_validator(mode="after")
    def binding_shape(self) -> AccountWriteRequest:
        expected_binding = {
            AccountAuthMethod.OFFICIAL_API: AccountBinding.SERVER_ENCRYPTED,
            AccountAuthMethod.BROWSER_AUTOMATION: AccountBinding.DESKTOP,
            AccountAuthMethod.ANDROID_DEVICE: AccountBinding.DEVICE,
            AccountAuthMethod.MANUAL_EXPORT: AccountBinding.SERVER_ENCRYPTED,
        }[self.auth_method]
        if self.binding is not expected_binding:
            raise ValueError("账号方式与凭据保存位置不匹配")

        has_secret = self.credential is not None and self.credential.has_value()
        has_handle = self.external_credential_ref is not None
        if self.credential_action is CredentialAction.REPLACE:
            if self.binding is AccountBinding.SERVER_ENCRYPTED:
                if not has_secret or has_handle:
                    raise ValueError("服务端加密绑定必须提供服务端凭据且不能提供外部 handle")
            elif not has_handle or self.credential is not None:
                raise ValueError("Desktop/Device 绑定只能提供外部安全存储 handle")
        elif self.credential is not None or has_handle:
            raise ValueError("只有替换凭据时才能提交凭据或外部 handle")

        if self.auth_method is AccountAuthMethod.MANUAL_EXPORT:
            if self.credential_action is CredentialAction.REPLACE:
                raise ValueError("手工导出账号不保存凭据")
        return self


class VaultView(BaseModel):
    state: VaultState
    initialized: bool
    unlocked: bool


class ProviderView(BaseModel):
    kind: ProviderKind
    provider_name: str
    model_name: str | None
    base_url: str | None
    enabled: bool
    options: dict[str, Any]
    credential_configured: bool
    readiness: Literal["DISABLED", "MISSING_CREDENTIAL", "CONFIGURED_UNVERIFIED"]
    row_version: int
    created_at: datetime
    updated_at: datetime


class PlatformAccountView(BaseModel):
    id: str
    platform: Platform
    display_name: str
    external_account_id: str
    auth_method: AccountAuthMethod
    binding: AccountBinding
    locale: str
    publishing_window: str | None
    enabled: bool
    credential_configured: bool
    verification_status: Literal["UNVERIFIED"] = "UNVERIFIED"
    row_version: int
    created_at: datetime
    updated_at: datetime


class SettingsSnapshot(BaseModel):
    vault: VaultView
    providers: list[ProviderView]
    accounts: list[PlatformAccountView]
    live_connections_enabled: Literal[False] = False


class SettingsGateway(Protocol):
    def snapshot(self) -> SettingsSnapshot: ...
    def initialize_vault(self, body: InitializeVaultRequest) -> VaultView: ...
    def unlock_vault(self, body: UnlockVaultRequest) -> VaultView: ...
    def lock_vault(self) -> VaultView: ...
    def upsert_provider(self, kind: ProviderKind, body: ProviderWriteRequest) -> ProviderView: ...
    def delete_provider(self, kind: ProviderKind, expected_version: int) -> None: ...
    def create_account(self, body: AccountWriteRequest) -> PlatformAccountView: ...
    def update_account(self, account_id: str, body: AccountWriteRequest) -> PlatformAccountView: ...
    def delete_account(self, account_id: str, expected_version: int) -> None: ...


class InvalidSettingsError(Exception):
    pass


class VaultNotInitializedError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _vault_envelope(record: VaultMetadataRecord) -> VaultEnvelope:
    return VaultEnvelope(
        crypto_version=record.crypto_version,
        kdf_name=record.kdf_name,
        kdf_parameters=record.kdf_parameters,
        salt=record.salt,
        wrapped_key_nonce=record.wrapped_key_nonce,
        wrapped_master_key=record.wrapped_master_key,
        wrapped_key_tag=record.wrapped_key_tag,
    )


def _credential_aad(
    *,
    credential_id: str,
    owner_type: str,
    owner_id: str,
    purpose: str,
) -> bytes:
    return (f"videoforge:credential:v1:{credential_id}:{owner_type}:{owner_id}:{purpose}").encode()


class DbSettingsGateway:
    def __init__(self, engine: Engine, vault: CredentialVault | None = None) -> None:
        self._engine = engine
        self._vault = vault or CredentialVault()

    @property
    def vault(self) -> CredentialVault:
        return self._vault

    def snapshot(self) -> SettingsSnapshot:
        with session_scope(self._engine) as session:
            repo = SettingsRepository(session)
            metadata = repo.get_vault_metadata()
            providers = [self._provider_view(repo, item) for item in repo.list_providers()]
            accounts = [self._account_view(repo, item) for item in repo.list_accounts()]
        return SettingsSnapshot(
            vault=self._vault_view(metadata is not None),
            providers=providers,
            accounts=accounts,
        )

    def initialize_vault(self, body: InitializeVaultRequest) -> VaultView:
        passphrase = body.passphrase.get_secret_value()
        envelope, master_key = self._vault.create_envelope(passphrase)
        now = _utcnow()
        record = VaultMetadataRecord(
            id=_VAULT_ID,
            crypto_version=envelope.crypto_version,
            kdf_name=envelope.kdf_name,
            kdf_parameters=envelope.kdf_parameters,
            salt=envelope.salt,
            wrapped_key_nonce=envelope.wrapped_key_nonce,
            wrapped_master_key=envelope.wrapped_master_key,
            wrapped_key_tag=envelope.wrapped_key_tag,
            created_at=now,
            updated_at=now,
        )
        try:
            with session_scope(self._engine) as session:
                SettingsRepository(session).create_vault_metadata(record)
            self._vault.activate(master_key)
        except BaseException:
            self._vault.wipe(master_key)
            raise
        return self._vault_view(True)

    def unlock_vault(self, body: UnlockVaultRequest) -> VaultView:
        with session_scope(self._engine) as session:
            metadata = SettingsRepository(session).get_vault_metadata()
        if metadata is None:
            raise VaultNotInitializedError("本地凭据库尚未初始化")
        self._vault.unlock(body.passphrase.get_secret_value(), _vault_envelope(metadata))
        return self._vault_view(True)

    def lock_vault(self) -> VaultView:
        self._vault.lock()
        with session_scope(self._engine) as session:
            initialized = SettingsRepository(session).get_vault_metadata() is not None
        return self._vault_view(initialized)

    def upsert_provider(self, kind: ProviderKind, body: ProviderWriteRequest) -> ProviderView:
        if body.credential_action is CredentialAction.KEEP:
            return self._upsert_provider_transaction(kind, body, key=None)
        with self._vault.lease() as key:
            return self._upsert_provider_transaction(kind, body, key=key)

    def _upsert_provider_transaction(
        self,
        kind: ProviderKind,
        body: ProviderWriteRequest,
        *,
        key: bytearray | None,
    ) -> ProviderView:
        now = _utcnow()
        with session_scope(self._engine) as session:
            repo = SettingsRepository(session)
            current = repo.get_provider(kind.value)
            if current is None:
                if body.expected_version is not None:
                    raise VersionConflictError(
                        "provider_configuration", kind.value, body.expected_version
                    )
                record = ProviderConfigurationRecord(
                    kind=kind.value,
                    provider_name=body.provider_name,
                    model_name=body.model_name,
                    base_url=body.base_url,
                    enabled=body.enabled,
                    options=body.options,
                    row_version=1,
                    created_at=now,
                    updated_at=now,
                )
                stored = repo.create_provider(record)
            else:
                if body.expected_version is None:
                    raise VersionConflictError(
                        "provider_configuration", kind.value, current.row_version
                    )
                record = ProviderConfigurationRecord(
                    kind=kind.value,
                    provider_name=body.provider_name,
                    model_name=body.model_name,
                    base_url=body.base_url,
                    enabled=body.enabled,
                    options=body.options,
                    row_version=current.row_version,
                    created_at=current.created_at,
                    updated_at=current.updated_at,
                )
                stored = repo.update_provider(
                    record,
                    expected_version=body.expected_version,
                )

            if body.credential_action is CredentialAction.REPLACE:
                assert key is not None and body.credential is not None
                self._store_server_credential(
                    repo,
                    key,
                    owner_type="PROVIDER",
                    owner_id=kind.value,
                    purpose=f"provider:{kind.value.lower()}",
                    credential=body.credential,
                )
            elif body.credential_action is CredentialAction.CLEAR:
                repo.clear_credential("PROVIDER", kind.value)
            return self._provider_view(repo, stored)

    def delete_provider(self, kind: ProviderKind, expected_version: int) -> None:
        with session_scope(self._engine) as session:
            configured = (
                SettingsRepository(session).get_credential("PROVIDER", kind.value) is not None
            )
        if configured:
            with self._vault.lease():
                with session_scope(self._engine) as session:
                    SettingsRepository(session).delete_provider(
                        kind.value, expected_version=expected_version
                    )
        else:
            with session_scope(self._engine) as session:
                SettingsRepository(session).delete_provider(
                    kind.value, expected_version=expected_version
                )

    def create_account(self, body: AccountWriteRequest) -> PlatformAccountView:
        if body.expected_version is not None:
            raise VersionConflictError("platform_account_binding", "new", body.expected_version)
        return self._write_account(None, body)

    def update_account(self, account_id: str, body: AccountWriteRequest) -> PlatformAccountView:
        if body.expected_version is None:
            raise InvalidSettingsError("更新账号必须提供 expected_version")
        return self._write_account(account_id, body)

    def _write_account(
        self,
        account_id: str | None,
        body: AccountWriteRequest,
    ) -> PlatformAccountView:
        previous_server_credential = False
        if account_id is not None:
            with session_scope(self._engine) as session:
                previous = SettingsRepository(session).get_credential("ACCOUNT", account_id)
                previous_server_credential = (
                    previous is not None
                    and previous.storage_kind == AccountBinding.SERVER_ENCRYPTED.value
                )
        needs_server_key = body.credential_action in {
            CredentialAction.REPLACE,
            CredentialAction.CLEAR,
        } and (body.binding is AccountBinding.SERVER_ENCRYPTED or previous_server_credential)
        if needs_server_key:
            with self._vault.lease() as key:
                return self._write_account_transaction(account_id, body, key=key)
        return self._write_account_transaction(account_id, body, key=None)

    def _write_account_transaction(
        self,
        account_id: str | None,
        body: AccountWriteRequest,
        *,
        key: bytearray | None,
    ) -> PlatformAccountView:
        now = _utcnow()
        with session_scope(self._engine) as session:
            repo = SettingsRepository(session)
            current = None if account_id is None else repo.get_account(account_id)
            if account_id is not None and current is None:
                raise NotFoundError("platform_account_binding", account_id)
            if (
                current is not None
                and body.credential_action is CredentialAction.KEEP
                and current.binding != body.binding.value
            ):
                raise InvalidSettingsError("改变凭据保存位置时必须明确替换或清除旧凭据")

            record = PlatformAccountBindingRecord(
                id=account_id or new_id(),
                platform=body.platform.value,
                display_name=body.display_name,
                external_account_id=body.external_account_id,
                auth_method=body.auth_method.value,
                binding=body.binding.value,
                locale=body.locale,
                publishing_window=body.publishing_window,
                enabled=body.enabled,
                verification_status="UNVERIFIED",
                row_version=1 if current is None else current.row_version,
                created_at=now if current is None else current.created_at,
                updated_at=now if current is None else current.updated_at,
            )
            if current is None:
                stored = repo.create_account(record)
            else:
                assert body.expected_version is not None
                stored = repo.update_account(
                    record,
                    expected_version=body.expected_version,
                )

            if body.credential_action is CredentialAction.REPLACE:
                if body.binding is AccountBinding.SERVER_ENCRYPTED:
                    assert key is not None and body.credential is not None
                    self._store_server_credential(
                        repo,
                        key,
                        owner_type="ACCOUNT",
                        owner_id=stored.id,
                        purpose=f"account:{body.platform.value.lower()}:official-api",
                        credential=body.credential,
                    )
                else:
                    assert body.external_credential_ref is not None
                    repo.replace_credential(
                        CredentialEntryRecord(
                            id=new_id(),
                            owner_type="ACCOUNT",
                            owner_id=stored.id,
                            storage_kind=body.binding.value,
                            purpose=f"account:{body.platform.value.lower()}:{body.auth_method.value.lower()}",
                            external_handle=body.external_credential_ref,
                            nonce=None,
                            ciphertext=None,
                            auth_tag=None,
                            created_at=now,
                            updated_at=now,
                        )
                    )
            elif body.credential_action is CredentialAction.CLEAR:
                repo.clear_credential("ACCOUNT", stored.id)
            return self._account_view(repo, stored)

    def delete_account(self, account_id: str, expected_version: int) -> None:
        with session_scope(self._engine) as session:
            credential = SettingsRepository(session).get_credential("ACCOUNT", account_id)
        needs_server_key = credential is not None and credential.storage_kind == "SERVER_ENCRYPTED"
        if needs_server_key:
            with self._vault.lease():
                with session_scope(self._engine) as session:
                    SettingsRepository(session).delete_account(
                        account_id, expected_version=expected_version
                    )
        else:
            with session_scope(self._engine) as session:
                SettingsRepository(session).delete_account(
                    account_id, expected_version=expected_version
                )

    def _store_server_credential(
        self,
        repo: SettingsRepository,
        key: bytearray,
        *,
        owner_type: str,
        owner_id: str,
        purpose: str,
        credential: SecretBundle,
    ) -> None:
        credential_id = new_id()
        aad = _credential_aad(
            credential_id=credential_id,
            owner_type=owner_type,
            owner_id=owner_id,
            purpose=purpose,
        )
        encrypted = self._vault.encrypt(key, credential.plaintext_json(), aad=aad)
        now = _utcnow()
        repo.replace_credential(
            CredentialEntryRecord(
                id=credential_id,
                owner_type=owner_type,
                owner_id=owner_id,
                storage_kind="SERVER_ENCRYPTED",
                purpose=purpose,
                external_handle=None,
                nonce=encrypted.nonce,
                ciphertext=encrypted.ciphertext,
                auth_tag=encrypted.auth_tag,
                created_at=now,
                updated_at=now,
            )
        )

    def _vault_view(self, initialized: bool) -> VaultView:
        if not initialized:
            state_value = VaultState.UNINITIALIZED
        elif self._vault.is_unlocked:
            state_value = VaultState.UNLOCKED
        else:
            state_value = VaultState.LOCKED
        return VaultView(
            state=state_value,
            initialized=initialized,
            unlocked=state_value is VaultState.UNLOCKED,
        )

    @staticmethod
    def _provider_view(
        repo: SettingsRepository,
        record: ProviderConfigurationRecord,
    ) -> ProviderView:
        configured = repo.get_credential("PROVIDER", record.kind) is not None
        readiness: Literal["DISABLED", "MISSING_CREDENTIAL", "CONFIGURED_UNVERIFIED"]
        if not record.enabled:
            readiness = "DISABLED"
        elif not configured:
            readiness = "MISSING_CREDENTIAL"
        else:
            readiness = "CONFIGURED_UNVERIFIED"
        return ProviderView(
            kind=ProviderKind(record.kind),
            provider_name=record.provider_name,
            model_name=record.model_name,
            base_url=record.base_url,
            enabled=record.enabled,
            options=record.options,
            credential_configured=configured,
            readiness=readiness,
            row_version=record.row_version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _account_view(
        repo: SettingsRepository,
        record: PlatformAccountBindingRecord,
    ) -> PlatformAccountView:
        return PlatformAccountView(
            id=record.id,
            platform=Platform(record.platform),
            display_name=record.display_name,
            external_account_id=record.external_account_id,
            auth_method=AccountAuthMethod(record.auth_method),
            binding=AccountBinding(record.binding),
            locale=record.locale,
            publishing_window=record.publishing_window,
            enabled=record.enabled,
            credential_configured=repo.get_credential("ACCOUNT", record.id) is not None,
            verification_status="UNVERIFIED",
            row_version=record.row_version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


def get_settings_gateway(request: Request) -> SettingsGateway:
    return request.app.state.settings_gateway


GatewayDep = Annotated[SettingsGateway, Depends(get_settings_gateway)]
router = APIRouter(prefix="/v1/settings", tags=["settings"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VaultNotInitializedError):
        return HTTPException(
            status_code=409,
            detail={"code": "VAULT_NOT_INITIALIZED", "message": "本地凭据库尚未初始化"},
        )
    if isinstance(exc, VaultLockedError):
        return HTTPException(
            status_code=423,
            detail={"code": "VAULT_LOCKED", "message": "本地凭据库已锁定"},
        )
    if isinstance(exc, VaultBusyError):
        return HTTPException(
            status_code=429,
            detail={"code": "VAULT_BUSY", "message": "凭据库繁忙，请稍后重试"},
        )
    if isinstance(exc, InvalidPassphraseError):
        return HTTPException(
            status_code=403,
            detail={"code": "VAULT_UNLOCK_FAILED", "message": "无法解锁本地凭据库"},
        )
    if isinstance(exc, NotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "SETTINGS_NOT_FOUND", "message": "设置记录不存在"},
        )
    if isinstance(exc, (VersionConflictError, DuplicateError)):
        return HTTPException(
            status_code=409,
            detail={
                "code": "SETTINGS_CONFLICT",
                "message": "设置已被修改或记录已存在，请重新载入",
            },
        )
    if isinstance(exc, InvalidSettingsError):
        return HTTPException(
            status_code=422,
            detail={"code": "INVALID_SETTINGS", "message": str(exc)},
        )
    return HTTPException(
        status_code=500,
        detail={"code": "SETTINGS_ERROR", "message": "设置操作失败"},
    )


_MAPPED_ERRORS = (
    DuplicateError,
    InvalidPassphraseError,
    InvalidSettingsError,
    NotFoundError,
    VaultBusyError,
    VaultLockedError,
    VaultNotInitializedError,
    VersionConflictError,
)


@router.get("")
def get_settings(gateway: GatewayDep) -> SettingsSnapshot:
    return gateway.snapshot()


@router.post("/vault:initialize")
def initialize_vault(body: InitializeVaultRequest, gateway: GatewayDep) -> VaultView:
    try:
        return gateway.initialize_vault(body)
    except _MAPPED_ERRORS as exc:
        raise _http_error(exc) from None


@router.post("/vault:unlock")
def unlock_vault(body: UnlockVaultRequest, gateway: GatewayDep) -> VaultView:
    try:
        return gateway.unlock_vault(body)
    except _MAPPED_ERRORS as exc:
        raise _http_error(exc) from None


@router.post("/vault:lock")
def lock_vault(gateway: GatewayDep) -> VaultView:
    try:
        return gateway.lock_vault()
    except _MAPPED_ERRORS as exc:
        raise _http_error(exc) from None


@router.put("/providers/{kind}")
def upsert_provider(
    kind: ProviderKind,
    body: ProviderWriteRequest,
    gateway: GatewayDep,
) -> ProviderView:
    try:
        return gateway.upsert_provider(kind, body)
    except _MAPPED_ERRORS as exc:
        raise _http_error(exc) from None


@router.delete("/providers/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(
    kind: ProviderKind,
    gateway: GatewayDep,
    expected_version: Annotated[int, Query(ge=1)],
) -> Response:
    try:
        gateway.delete_provider(kind, expected_version)
    except _MAPPED_ERRORS as exc:
        raise _http_error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(
    body: AccountWriteRequest,
    gateway: GatewayDep,
) -> PlatformAccountView:
    try:
        return gateway.create_account(body)
    except _MAPPED_ERRORS as exc:
        raise _http_error(exc) from None


@router.put("/accounts/{account_id}")
def update_account(
    account_id: str,
    body: AccountWriteRequest,
    gateway: GatewayDep,
) -> PlatformAccountView:
    try:
        return gateway.update_account(account_id, body)
    except _MAPPED_ERRORS as exc:
        raise _http_error(exc) from None


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: str,
    gateway: GatewayDep,
    expected_version: Annotated[int, Query(ge=1)],
) -> Response:
    try:
        gateway.delete_account(account_id, expected_version)
    except _MAPPED_ERRORS as exc:
        raise _http_error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def redacted_validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """FastAPI 默认 422 会回显 `input`；这里只返回字段位置、类型和通用文案。"""

    details = []
    for error in exc.errors():
        details.append(
            {
                "loc": list(error.get("loc", ())),
                "type": error.get("type", "validation_error"),
                "msg": "输入格式或取值不符合要求",
            }
        )
    return JSONResponse(status_code=422, content={"detail": details})


__all__ = [
    "AccountAuthMethod",
    "AccountBinding",
    "AccountWriteRequest",
    "CredentialAction",
    "DbSettingsGateway",
    "InitializeVaultRequest",
    "Platform",
    "PlatformAccountView",
    "ProviderKind",
    "ProviderView",
    "ProviderWriteRequest",
    "SecretBundle",
    "SettingsGateway",
    "SettingsSnapshot",
    "UnlockVaultRequest",
    "VaultState",
    "VaultView",
    "redacted_validation_error_handler",
    "router",
]
