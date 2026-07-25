"""/v1/projects 路由层（stub gateway）：分析触发的状态码语义与产物路径映射。"""

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from videoforge_api.analysis_service import SourceNotAnalyzable, UnsupportedAnalysisLanguage
from videoforge_api.main import create_app
from videoforge_api.projects import AnalysisRunView, RunAnalysisRequest
from videoforge_contracts import CreationMode, Project, ProjectStatus
from videoforge_persistence import NotFoundError

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _project(pid: str = "p1") -> Project:
    return Project(
        id=pid,
        title="演示项目",
        vertical="ai-tech",
        source_language="zh-CN",
        target_languages=["en-US"],
        creation_mode=CreationMode.STRUCTURE_REWRITE,
        status=ProjectStatus.DRAFT,
        created_at=_T0,
        updated_at=_T0,
    )


class StubProjectGateway:
    def list_projects(self, limit: int) -> list[Project]:
        return [_project("p1"), _project("p2")][:limit]

    def get_project(self, project_id: str) -> Project:
        if project_id == "missing":
            raise NotFoundError("project", project_id)
        return _project(project_id)

    def run_analysis(self, project_id: str, request: RunAnalysisRequest) -> AnalysisRunView:
        if request.source_asset_id == "no-file":
            raise SourceNotAnalyzable("素材尚无本地文件；请先人工下载关联")
        if request.language == "ja-JP":
            raise UnsupportedAnalysisLanguage("无 ja-JP 的 Fake 录制")
        if project_id == "missing":
            raise NotFoundError("project", project_id)
        return AnalysisRunView(
            id="run-1",
            project_id=project_id,
            source_asset_id=request.source_asset_id,
            language=request.language,
            status="COMPLETED",
            stages=[
                {
                    "stage": "transcript",
                    "status": "COMPLETED",
                    "cache_hit": True,
                    "artifact_id": "art-1",
                    "provider": "fake-asr",
                }
            ],
        )

    def latest_analysis(self, project_id: str) -> AnalysisRunView:
        if project_id == "never":
            raise NotFoundError("analysis_run", project_id)
        return self.run_analysis(
            project_id, RunAnalysisRequest(source_asset_id="a1", language="zh-CN")
        )

    def analysis_artifact(self, project_id: str, kind: str) -> dict[str, Any]:
        if kind == "video_blueprint":
            raise NotFoundError("analysis_artifact", kind)
        return {"kind": kind}


def _client() -> TestClient:
    app = create_app()
    app.state.project_gateway = StubProjectGateway()
    return TestClient(app)


def test_list_and_get_project() -> None:
    client = _client()
    assert len(client.get("/v1/projects").json()) == 2
    assert len(client.get("/v1/projects?limit=1").json()) == 1
    assert client.get("/v1/projects/p1").json()["id"] == "p1"
    assert client.get("/v1/projects/missing").status_code == 404


def test_run_analysis_status_codes() -> None:
    client = _client()
    ok = client.post(
        "/v1/projects/p1/analysis:run", json={"source_asset_id": "a1", "language": "zh-CN"}
    )
    assert ok.status_code == 200
    assert ok.json()["stages"][0]["cache_hit"] is True

    conflict = client.post(
        "/v1/projects/p1/analysis:run", json={"source_asset_id": "no-file", "language": "zh-CN"}
    )
    assert conflict.status_code == 409
    assert "本地文件" in conflict.json()["detail"]

    unsupported = client.post(
        "/v1/projects/p1/analysis:run", json={"source_asset_id": "a1", "language": "ja-JP"}
    )
    assert unsupported.status_code == 422


def test_latest_analysis_and_artifacts() -> None:
    client = _client()
    assert client.get("/v1/projects/p1/analysis").json()["status"] == "COMPLETED"
    assert client.get("/v1/projects/never/analysis").status_code == 404
    assert client.get("/v1/projects/p1/analysis/transcript").json()["kind"] == "transcript"
    assert client.get("/v1/projects/p1/analysis/text-tracks").json()["kind"] == "text_track_set"
    assert client.get("/v1/projects/p1/analysis/visual").json()["kind"] == "visual_analysis"
    assert client.get("/v1/projects/p1/analysis/blueprint").status_code == 404
    assert client.get("/v1/projects/p1/analysis/unknown-thing").status_code == 404
