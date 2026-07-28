from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from videoforge_api.artifact_uploads import (
    ArtifactCommitRequest,
    ArtifactStageView,
    ArtifactUploadStateError,
)
from videoforge_api.main import create_app
from videoforge_contracts import Artifact, StorageRef

pytestmark = pytest.mark.no_db


class StubUploadGateway:
    def stage(self, job_id: str) -> ArtifactStageView:
        if job_id == "denied":
            raise ArtifactUploadStateError("UNKNOWN 使用依据禁止对象写入")
        return ArtifactStageView(
            upload_id="upload-1",
            put_url="https://minio.invalid/staging/upload-1?signature=redacted",
            expires_at="2026-07-27T12:00:00+00:00",
        )

    def commit(self, job_id: str, upload_id: str, request: ArtifactCommitRequest) -> Artifact:
        return Artifact(
            id="artifact-1",
            kind="source_video",
            filename=request.filename,
            mime_type=request.mime_type,
            size_bytes=request.size_bytes,
            sha256=request.sha256,
            storage=StorageRef(
                backend="s3",
                bucket="videoforge",
                object_key="artifacts/default/_unassigned/artifact-1/source.mp4",
            ),
            created_at=datetime.now(UTC),
        )


def _client() -> TestClient:
    app = create_app()
    app.state.artifact_upload_gateway = StubUploadGateway()
    return TestClient(app)


def test_stage_is_job_scoped_and_never_cacheable() -> None:
    response = _client().post("/v1/ingest/jobs/job-1/artifact-uploads")
    assert response.status_code == 201
    assert response.json()["upload_id"] == "upload-1"
    assert response.headers["cache-control"] == "no-store"
    assert _client().post("/v1/ingest/jobs/denied/artifact-uploads").status_code == 409


def test_commit_contract_requires_mp4_integrity_declarations() -> None:
    response = _client().post(
        "/v1/ingest/jobs/job-1/artifact-uploads/upload-1/commit",
        json={
            "filename": "source.mp4",
            "mime_type": "video/mp4",
            "sha256": "a" * 64,
            "size_bytes": 1546,
        },
    )
    assert response.status_code == 201
    assert response.json()["kind"] == "source_video"
    invalid = _client().post(
        "/v1/ingest/jobs/job-1/artifact-uploads/upload-1/commit",
        json={
            "filename": "source.exe",
            "mime_type": "application/octet-stream",
            "sha256": "bad",
            "size_bytes": 0,
        },
    )
    assert invalid.status_code == 422
