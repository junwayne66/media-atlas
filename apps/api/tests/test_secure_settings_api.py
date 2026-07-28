"""M-W10 设置路由合同：状态码、零回显与永不在线验证。"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from videoforge_api.credential_vault import InvalidPassphraseError, VaultLockedError
from videoforge_api.main import create_app
from videoforge_api.secure_settings import (
    AccountWriteRequest,
    InitializeVaultRequest,
    PlatformAccountView,
    ProviderKind,
    ProviderView,
    ProviderWriteRequest,
    SettingsSnapshot,
    UnlockVaultRequest,
    VaultState,
    VaultView,
)
from videoforge_persistence import VersionConflictError

pytestmark = pytest.mark.no_db

T0 = datetime(2026, 7, 27, tzinfo=UTC)


def _provider(version: int = 1) -> ProviderView:
    return ProviderView(
        kind="LLM",
        provider_name="synthetic",
        model_name="model",
        base_url="https://example.invalid/v1",
        enabled=True,
        options={},
        credential_configured=True,
        readiness="CONFIGURED_UNVERIFIED",
        row_version=version,
        created_at=T0,
        updated_at=T0,
    )


def _account(version: int = 1) -> PlatformAccountView:
    return PlatformAccountView(
        id="account-1",
        platform="DOUYIN",
        display_name="合成账号",
        external_account_id="synthetic",
        auth_method="OFFICIAL_API",
        binding="SERVER_ENCRYPTED",
        locale="zh-CN",
        publishing_window=None,
        enabled=False,
        credential_configured=True,
        verification_status="UNVERIFIED",
        row_version=version,
        created_at=T0,
        updated_at=T0,
    )


class StubSettingsGateway:
    def snapshot(self) -> SettingsSnapshot:
        return SettingsSnapshot(
            vault=VaultView(state=VaultState.LOCKED, initialized=True, unlocked=False),
            providers=[_provider()],
            accounts=[_account()],
        )

    def initialize_vault(self, body: InitializeVaultRequest) -> VaultView:
        return VaultView(state=VaultState.UNLOCKED, initialized=True, unlocked=True)

    def unlock_vault(self, body: UnlockVaultRequest) -> VaultView:
        if body.passphrase.get_secret_value().startswith("wrong"):
            raise InvalidPassphraseError("internal crypto message")
        return VaultView(state=VaultState.UNLOCKED, initialized=True, unlocked=True)

    def lock_vault(self) -> VaultView:
        return VaultView(state=VaultState.LOCKED, initialized=True, unlocked=False)

    def upsert_provider(
        self, kind: ProviderKind, body: ProviderWriteRequest
    ) -> ProviderView:
        if body.provider_name == "conflict":
            raise VersionConflictError("provider_configuration", kind.value, 1)
        if body.credential_action.value == "REPLACE" and body.provider_name == "locked":
            raise VaultLockedError("internal lock message")
        return _provider(version=(body.expected_version or 0) + 1)

    def delete_provider(self, kind: ProviderKind, expected_version: int) -> None:
        return None

    def create_account(self, body: AccountWriteRequest) -> PlatformAccountView:
        return _account()

    def update_account(
        self, account_id: str, body: AccountWriteRequest
    ) -> PlatformAccountView:
        return _account(version=(body.expected_version or 0) + 1)

    def delete_account(self, account_id: str, expected_version: int) -> None:
        return None


def _client() -> TestClient:
    app = create_app()
    app.state.settings_gateway = StubSettingsGateway()
    return TestClient(app)


def test_snapshot_is_nonsecret_and_no_store() -> None:
    response = _client().get("/v1/settings")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    raw = response.text.lower()
    assert "credential_ref" not in raw
    assert "api_key" not in raw
    assert response.json()["accounts"][0]["verification_status"] == "UNVERIFIED"
    assert response.json()["live_connections_enabled"] is False


def test_vault_actions_and_generic_wrong_passphrase_error() -> None:
    client = _client()
    initialized = client.post(
        "/v1/settings/vault:initialize",
        json={
            "passphrase": "synthetic-passphrase-2026",
            "confirmation": "synthetic-passphrase-2026",
        },
    )
    assert initialized.status_code == 200
    assert initialized.json()["state"] == "UNLOCKED"
    assert client.post("/v1/settings/vault:lock").json()["state"] == "LOCKED"

    canary = "wrong-VF_SECRET_CANARY"
    failed = client.post(
        "/v1/settings/vault:unlock",
        json={"passphrase": canary},
    )
    assert failed.status_code == 403
    assert failed.json()["detail"]["code"] == "VAULT_UNLOCK_FAILED"
    assert canary not in failed.text


def test_validation_errors_scrub_secret_input_and_reject_cookie_field() -> None:
    client = _client()
    canary = "VF_SECRET_CANARY_" + ("x" * 17000)
    invalid = client.put(
        "/v1/settings/providers/LLM",
        json={
            "provider_name": "synthetic",
            "enabled": True,
            "expected_version": None,
            "credential_action": "REPLACE",
            "credential": {"api_key": canary},
        },
    )
    assert invalid.status_code == 422
    assert "VF_SECRET_CANARY_" not in invalid.text
    assert '"input"' not in invalid.text

    cookie = "VF_COOKIE_CANARY=value"
    rejected = client.post(
        "/v1/settings/accounts",
        json={
            "platform": "DOUYIN",
            "display_name": "合成账号",
            "external_account_id": "synthetic",
            "auth_method": "BROWSER_AUTOMATION",
            "binding": "DESKTOP",
            "locale": "zh-CN",
            "enabled": False,
            "expected_version": None,
            "credential_action": "REPLACE",
            "external_credential_ref": "douyin-main-cookie",
            "cookie": cookie,
        },
    )
    assert rejected.status_code == 422
    assert cookie not in rejected.text


def test_provider_conflict_locked_and_delete_status_codes() -> None:
    client = _client()
    conflict = client.put(
        "/v1/settings/providers/LLM",
        json={
            "provider_name": "conflict",
            "enabled": False,
            "expected_version": 1,
            "credential_action": "KEEP",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "SETTINGS_CONFLICT"

    locked = client.put(
        "/v1/settings/providers/LLM",
        json={
            "provider_name": "locked",
            "enabled": True,
            "expected_version": 1,
            "credential_action": "REPLACE",
            "credential": {"api_key": "synthetic-key"},
        },
    )
    assert locked.status_code == 423
    assert locked.json()["detail"]["code"] == "VAULT_LOCKED"
    assert client.delete("/v1/settings/providers/LLM?expected_version=1").status_code == 204


def test_desktop_account_accepts_only_handle_and_stays_unverified() -> None:
    client = _client()
    response = client.post(
        "/v1/settings/accounts",
        json={
            "platform": "TIKTOK",
            "display_name": "合成 TikTok",
            "external_account_id": "synthetic-tiktok",
            "auth_method": "BROWSER_AUTOMATION",
            "binding": "DESKTOP",
            "locale": "en-US",
            "enabled": False,
            "expected_version": None,
            "credential_action": "REPLACE",
            "external_credential_ref": "tiktok.desktop.main",
        },
    )
    assert response.status_code == 201
    assert response.json()["verification_status"] == "UNVERIFIED"
    assert "external_credential_ref" not in response.text
    assert "tiktok.desktop.main" not in response.text


def test_desktop_and_device_handles_reject_path_or_protocol_semantics() -> None:
    client = _client()
    base = {
        "platform": "DOUYIN",
        "display_name": "合成账号",
        "external_account_id": "synthetic",
        "auth_method": "BROWSER_AUTOMATION",
        "binding": "DESKTOP",
        "locale": "zh-CN",
        "credential_action": "REPLACE",
    }
    for unsafe in (
        "/Users/me/browser-profile",
        "../browser-profile",
        "file:///tmp/profile",
        "keychain://browser/main",
        "C:\\Users\\profile",
    ):
        response = client.post(
            "/v1/settings/accounts",
            json={**base, "external_credential_ref": unsafe},
        )
        assert response.status_code == 422
