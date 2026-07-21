from fastapi.testclient import TestClient

from videoforge_api.main import create_app


def test_healthz_reports_ok() -> None:
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "videoforge-api"


def test_v1_root_reports_api_version() -> None:
    client = TestClient(create_app())
    resp = client.get("/v1")
    assert resp.status_code == 200
    assert resp.json()["api_version"] == "v1"
