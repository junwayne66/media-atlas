"""真实 PostgreSQL + crypto gateway 的 M-W10 安全验收。"""

import json
import logging

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from videoforge_api.main import create_app
from videoforge_api.secure_settings import DbSettingsGateway

PASSPHRASE = "synthetic-integration-passphrase-2026"
CANARY = "VF_SECRET_CANARY_INTEGRATION_7e8d"


def _client(engine: Engine, gateway: DbSettingsGateway | None = None) -> TestClient:
    app = create_app()
    app.state.settings_gateway = gateway or DbSettingsGateway(engine)
    return TestClient(app)


def _initialize(client: TestClient) -> None:
    response = client.post(
        "/v1/settings/vault:initialize",
        json={"passphrase": PASSPHRASE, "confirmation": PASSPHRASE},
    )
    assert response.status_code == 200, response.text


def _provider_body(
    kind: str,
    *,
    expected_version: int | None,
    action: str,
    canary: str | None = None,
) -> dict:
    body = {
        "provider_name": f"synthetic-{kind.lower()}",
        "model_name": f"model-{kind.lower()}",
        "base_url": "https://example.invalid/v1",
        "enabled": True,
        "options": {"temperature": 0.2},
        "expected_version": expected_version,
        "credential_action": action,
    }
    if canary is not None:
        body["credential"] = {"api_key": canary}
    return body


def _assert_database_has_no_plaintext(engine: Engine, value: str) -> None:
    needle = value.encode()
    with engine.connect() as conn:
        for table_name in (
            "credential_vault_metadata",
            "credential_entries",
            "provider_configurations",
            "platform_account_bindings",
        ):
            rows = conn.execute(text(f"SELECT * FROM {table_name}")).mappings().all()
            for row in rows:
                for cell in row.values():
                    if isinstance(cell, bytes):
                        assert needle not in cell
                    elif isinstance(cell, (dict, list)):
                        assert value not in json.dumps(cell, ensure_ascii=False)
                    elif cell is not None:
                        assert value not in str(cell)


def test_provider_lifecycle_restart_lock_and_zero_plaintext(
    migrated_engine: Engine,
    caplog,
) -> None:
    caplog.set_level(logging.DEBUG)
    gateway = DbSettingsGateway(migrated_engine)
    client = _client(migrated_engine, gateway)
    assert client.get("/v1/settings").json()["vault"]["state"] == "UNINITIALIZED"
    _initialize(client)

    for kind in ("LLM", "ASR", "VLM"):
        secret = f"{CANARY}_{kind}"
        created = client.put(
            f"/v1/settings/providers/{kind}",
            json=_provider_body(
                kind,
                expected_version=None,
                action="REPLACE",
                canary=secret,
            ),
        )
        assert created.status_code == 200, created.text
        assert created.json()["credential_configured"] is True
        assert secret not in created.text

    snapshot = client.get("/v1/settings")
    assert snapshot.status_code == 200
    assert CANARY not in snapshot.text
    assert "credential_ref" not in snapshot.text
    _assert_database_has_no_plaintext(migrated_engine, CANARY)
    assert CANARY not in caplog.text

    with migrated_engine.connect() as conn:
        original_ciphertext = conn.execute(
            text(
                "SELECT ciphertext FROM credential_entries "
                "WHERE owner_type='PROVIDER' AND owner_id='LLM'"
            )
        ).scalar_one()

    kept = client.put(
        "/v1/settings/providers/LLM",
        json=_provider_body("LLM", expected_version=1, action="KEEP"),
    )
    assert kept.status_code == 200
    assert kept.json()["row_version"] == 2
    with migrated_engine.connect() as conn:
        kept_ciphertext = conn.execute(
            text(
                "SELECT ciphertext FROM credential_entries "
                "WHERE owner_type='PROVIDER' AND owner_id='LLM'"
            )
        ).scalar_one()
    assert kept_ciphertext == original_ciphertext

    stale = client.put(
        "/v1/settings/providers/LLM",
        json=_provider_body("LLM", expected_version=1, action="KEEP"),
    )
    assert stale.status_code == 409

    client.post("/v1/settings/vault:lock")
    locked = client.put(
        "/v1/settings/providers/LLM",
        json=_provider_body(
            "LLM",
            expected_version=2,
            action="REPLACE",
            canary=f"{CANARY}_replacement",
        ),
    )
    assert locked.status_code == 423
    assert CANARY not in locked.text

    # 新 gateway 模拟 API 进程重启：元数据仍可读，但解锁态不继承。
    restarted = _client(migrated_engine)
    restarted_snapshot = restarted.get("/v1/settings")
    assert restarted_snapshot.json()["vault"]["state"] == "LOCKED"
    wrong = restarted.post(
        "/v1/settings/vault:unlock",
        json={"passphrase": f"wrong-{CANARY}"},
    )
    assert wrong.status_code == 403
    assert CANARY not in wrong.text
    assert (
        restarted.post(
            "/v1/settings/vault:unlock",
            json={"passphrase": PASSPHRASE},
        ).status_code
        == 200
    )

    cleared = restarted.put(
        "/v1/settings/providers/LLM",
        json=_provider_body("LLM", expected_version=2, action="CLEAR"),
    )
    assert cleared.status_code == 200
    assert cleared.json()["credential_configured"] is False
    assert (
        restarted.delete("/v1/settings/providers/LLM?expected_version=3").status_code
        == 204
    )
    with migrated_engine.connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM credential_entries "
                    "WHERE owner_type='PROVIDER' AND owner_id='LLM'"
                )
            ).scalar_one()
            == 0
        )


def test_platform_binding_storage_loci_and_atomic_delete(migrated_engine: Engine) -> None:
    client = _client(migrated_engine)
    _initialize(client)

    official = client.post(
        "/v1/settings/accounts",
        json={
            "platform": "DOUYIN",
            "display_name": "合成抖音账号",
            "external_account_id": "douyin-synthetic",
            "auth_method": "OFFICIAL_API",
            "binding": "SERVER_ENCRYPTED",
            "locale": "zh-CN",
            "enabled": False,
            "expected_version": None,
            "credential_action": "REPLACE",
            "credential": {
                "access_token": f"{CANARY}_access",
                "refresh_token": f"{CANARY}_refresh",
            },
        },
    )
    assert official.status_code == 201, official.text
    assert official.json()["verification_status"] == "UNVERIFIED"
    assert CANARY not in official.text
    official_id = official.json()["id"]

    desktop_handle = "tiktok.desktop.synthetic"
    desktop = client.post(
        "/v1/settings/accounts",
        json={
            "platform": "TIKTOK",
            "display_name": "合成 TikTok 账号",
            "external_account_id": "tiktok-synthetic",
            "auth_method": "BROWSER_AUTOMATION",
            "binding": "DESKTOP",
            "locale": "en-US",
            "enabled": False,
            "expected_version": None,
            "credential_action": "REPLACE",
            "external_credential_ref": desktop_handle,
        },
    )
    assert desktop.status_code == 201, desktop.text
    assert desktop_handle not in desktop.text
    desktop_id = desktop.json()["id"]

    with migrated_engine.connect() as conn:
        locator = conn.execute(
            text(
                "SELECT external_handle, nonce, ciphertext, auth_tag "
                "FROM credential_entries WHERE owner_id=:owner_id"
            ),
            {"owner_id": desktop_id},
        ).mappings().one()
        assert locator["external_handle"] == desktop_handle
        assert locator["nonce"] is locator["ciphertext"] is locator["auth_tag"] is None

    _assert_database_has_no_plaintext(migrated_engine, CANARY)
    assert (
        client.delete(
            f"/v1/settings/accounts/{official_id}?expected_version=1"
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/v1/settings/accounts/{desktop_id}?expected_version=1"
        ).status_code
        == 204
    )
    with migrated_engine.connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM credential_entries "
                    "WHERE owner_id IN (:official_id, :desktop_id)"
                ),
                {"official_id": official_id, "desktop_id": desktop_id},
            ).scalar_one()
            == 0
        )


def test_duplicate_initialize_and_secret_options_are_rejected_without_echo(
    migrated_engine: Engine,
) -> None:
    client = _client(migrated_engine)
    _initialize(client)
    duplicate = client.post(
        "/v1/settings/vault:initialize",
        json={"passphrase": PASSPHRASE, "confirmation": PASSPHRASE},
    )
    assert duplicate.status_code == 409
    assert PASSPHRASE not in duplicate.text

    rejected = client.put(
        "/v1/settings/providers/LLM",
        json={
            "provider_name": "synthetic",
            "enabled": True,
            "options": {"api_key": CANARY},
            "expected_version": None,
            "credential_action": "KEEP",
        },
    )
    assert rejected.status_code == 422
    assert CANARY not in rejected.text
