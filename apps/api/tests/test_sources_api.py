"""/v1/sources 路由层（stub gateway）：状态码与错误语义。"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from videoforge_api.main import create_app
from videoforge_api.sources import (
    DuplicateGroupView,
    ImportFileRequest,
    ImportUrlRequest,
    LocalFileMissing,
    ResolveRequest,
    ResolveResponse,
)
from videoforge_contracts import SourceAsset, SourceAssetKind, SourceDisposition
from videoforge_persistence import NotFoundError

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _asset(asset_id: str = "a1", **over) -> SourceAsset:
    values = dict(
        id=asset_id,
        kind=SourceAssetKind.URL,
        original_input="https://www.douyin.com/video/7412345678901234567",
        platform="douyin",
        content_id="7412345678901234567",
        disposition=SourceDisposition.MANUAL_FALLBACK,
        reason="实时下载未配置",
        created_at=_T0,
        updated_at=_T0,
    )
    values.update(over)
    return SourceAsset(**values)


class StubSourceGateway:
    def __init__(self) -> None:
        self.existing = False

    def resolve(self, request: ResolveRequest) -> ResolveResponse:
        return ResolveResponse(resolvable=True, platform="douyin", reason="ok")

    def import_url(self, request: ImportUrlRequest) -> tuple[SourceAsset, bool]:
        created = not self.existing
        self.existing = True
        return _asset(), created

    def import_file(self, request: ImportFileRequest) -> tuple[SourceAsset, bool]:
        if request.path == "/missing.mp4":
            raise LocalFileMissing("本地文件不存在：/missing.mp4")
        return _asset(
            "a2",
            kind=SourceAssetKind.LOCAL_FILE,
            platform="manual",
            disposition=SourceDisposition.IMPORTED,
            reason="已导入",
            file_sha256="a" * 64,
        ), True

    def list_assets(self, platform, disposition, limit) -> list[SourceAsset]:
        assets = [_asset("a1"), _asset("a2", platform="tiktok")]
        if platform is not None:
            assets = [a for a in assets if a.platform == platform]
        return assets[:limit]

    def get_asset(self, asset_id: str) -> SourceAsset:
        if asset_id == "missing":
            raise NotFoundError("source_asset", asset_id)
        return _asset(asset_id)

    def duplicate_groups(self) -> list[DuplicateGroupView]:
        return [
            DuplicateGroupView(
                group_id="dg-1", member_asset_ids=["a1", "a2"], layers=["FILE"], similarity=1.0
            )
        ]


def _client() -> tuple[TestClient, StubSourceGateway]:
    app = create_app()
    stub = StubSourceGateway()
    app.state.source_gateway = stub
    return TestClient(app), stub


def test_resolve_is_preview_only() -> None:
    client, _ = _client()
    resp = client.post("/v1/sources:resolve", json={"input": "https://www.douyin.com/video/1"})
    assert resp.status_code == 200
    assert resp.json()["resolvable"] is True


def test_import_url_201_then_200_on_idempotent_hit() -> None:
    client, _ = _client()
    body = {"input": "https://www.douyin.com/video/7412345678901234567"}
    assert client.post("/v1/sources/import-url", json=body).status_code == 201
    second = client.post("/v1/sources/import-url", json=body)
    assert second.status_code == 200
    assert second.json()["id"] == "a1"


def test_import_file_missing_path_is_422() -> None:
    client, _ = _client()
    resp = client.post("/v1/sources/import-file", json={"path": "/missing.mp4"})
    assert resp.status_code == 422
    assert "不存在" in resp.json()["detail"]


def test_list_and_get_and_404() -> None:
    client, _ = _client()
    assert len(client.get("/v1/sources").json()) == 2
    assert len(client.get("/v1/sources?platform=tiktok").json()) == 1
    assert client.get("/v1/sources/a1").json()["id"] == "a1"
    assert client.get("/v1/sources/missing").status_code == 404


def test_duplicate_groups_route_not_shadowed_by_asset_id() -> None:
    client, _ = _client()
    resp = client.get("/v1/sources/duplicate-groups")
    assert resp.status_code == 200
    assert resp.json()[0]["member_asset_ids"] == ["a1", "a2"]
