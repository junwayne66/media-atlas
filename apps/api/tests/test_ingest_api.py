from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from videoforge_api.ingest import (
    AcquisitionStartRequest,
    DiscoveryStartRequest,
    IngestControlError,
    ResolveStartRequest,
)
from videoforge_api.main import create_app
from videoforge_contracts import (
    IngestJob,
    IngestJobEvent,
    IngestJobStatus,
    IngestJobType,
)
from videoforge_persistence import NotFoundError

pytestmark = pytest.mark.no_db


def _job(
    *,
    job_id: str = "job-1",
    job_type: IngestJobType = IngestJobType.DISCOVERY_SEARCH,
    status: IngestJobStatus = IngestJobStatus.PENDING,
) -> IngestJob:
    now = datetime.now(UTC)
    return IngestJob(
        id=job_id,
        job_type=job_type,
        status=status,
        platform="douyin",
        idempotency_key="idem-1",
        workflow_id=f"ingest-{job_id}",
        created_at=now,
        updated_at=now,
    )


class StubIngestService:
    def __init__(self) -> None:
        self.jobs = {
            "job-1": _job(),
            "needs-human": _job(
                job_id="needs-human", status=IngestJobStatus.NEED_HUMAN
            ),
            "done": _job(job_id="done", status=IngestJobStatus.SUCCEEDED),
        }

    async def start_discovery(
        self, idempotency_key: str, request: DiscoveryStartRequest
    ) -> IngestJob:
        assert idempotency_key == "idem-1"
        assert request.query == "番茄炒蛋"
        return self.jobs["job-1"]

    async def start_resolve(
        self, idempotency_key: str, request: ResolveStartRequest
    ) -> IngestJob:
        assert idempotency_key == "idem-1"
        return _job(job_type=IngestJobType.CONTENT_RESOLVE)

    async def start_acquisition(
        self,
        source_asset_id: str,
        idempotency_key: str,
        request: AcquisitionStartRequest,
    ) -> IngestJob:
        if not request.rights_basis.permits_acquisition:
            raise IngestControlError("UNKNOWN 使用依据不能创建媒体获取任务")
        return _job(job_type=IngestJobType.MEDIA_ACQUIRE)

    def get(self, job_id: str) -> IngestJob:
        try:
            return self.jobs[job_id]
        except KeyError:
            raise NotFoundError("ingest_job", job_id) from None

    def events(self, job_id: str) -> list[IngestJobEvent]:
        job = self.get(job_id)
        return [
            IngestJobEvent(
                id="event-1",
                job_id=job.id,
                event_type="ingest.job.created",
                to_status=IngestJobStatus.PENDING,
                created_at=job.created_at,
            )
        ]

    async def resume(self, job_id: str) -> IngestJob:
        job = self.get(job_id)
        if job.status is not IngestJobStatus.NEED_HUMAN:
            raise IngestControlError("只有 NEED_HUMAN 任务可以恢复")
        return job

    async def cancel(self, job_id: str) -> IngestJob:
        job = self.get(job_id)
        if job.status is IngestJobStatus.SUCCEEDED:
            raise IngestControlError("终态任务不能取消")
        return job


def _client() -> TestClient:
    app = create_app()
    app.state.ingest_service = StubIngestService()
    return TestClient(app)


def test_discovery_and_resolve_return_202() -> None:
    client = _client()
    discovery = client.post(
        "/v1/ingest/discovery",
        headers={"Idempotency-Key": "idem-1"},
        json={"query": "番茄炒蛋", "fixture": "board"},
    )
    assert discovery.status_code == 202
    assert discovery.json()["job_id"] == "job-1"
    assert discovery.json()["workflow_id"] == "ingest-job-1"

    resolve = client.post(
        "/v1/ingest/resolve",
        headers={"Idempotency-Key": "idem-1"},
        json={"url": "https://www.douyin.com/video/1234567890123456789"},
    )
    assert resolve.status_code == 202
    assert resolve.json()["job_type"] == "CONTENT_RESOLVE"


def test_start_requires_idempotency_header_and_strict_input() -> None:
    client = _client()
    missing = client.post("/v1/ingest/discovery", json={"query": "x"})
    assert missing.status_code == 422
    blank = client.post(
        "/v1/ingest/discovery",
        headers={"Idempotency-Key": "idem-1"},
        json={"query": ""},
    )
    assert blank.status_code == 422
    unsafe = client.post(
        "/v1/ingest/resolve",
        headers={"Idempotency-Key": "idem-1"},
        json={"url": "http://127.0.0.1/video/1"},
    )
    assert unsafe.status_code == 422
    path_like_profile = client.post(
        "/v1/ingest/discovery",
        headers={"Idempotency-Key": "idem-1"},
        json={"query": "x", "profile_id": "/Users/me/profile"},
    )
    assert path_like_profile.status_code == 422


def test_get_job_and_append_only_events() -> None:
    client = _client()
    job = client.get("/v1/ingest/jobs/job-1")
    assert job.status_code == 200
    assert job.json()["status"] == "PENDING"
    events = client.get("/v1/ingest/jobs/job-1/events")
    assert events.status_code == 200
    assert [event["event_type"] for event in events.json()] == ["ingest.job.created"]
    assert client.get("/v1/ingest/jobs/missing").status_code == 404


def test_resume_and_cancel_state_guards() -> None:
    client = _client()
    assert client.post("/v1/ingest/jobs/needs-human/resume").status_code == 202
    assert client.post("/v1/ingest/jobs/job-1/resume").status_code == 409
    assert client.post("/v1/ingest/jobs/job-1/cancel").status_code == 202
    assert client.post("/v1/ingest/jobs/done/cancel").status_code == 409


def test_acquisition_requires_explicit_rights_basis() -> None:
    client = _client()
    denied = client.post(
        "/v1/ingest/sources/source-1/acquisitions",
        headers={"Idempotency-Key": "idem-1"},
        json={"rights_basis": "UNKNOWN"},
    )
    assert denied.status_code == 409
    accepted = client.post(
        "/v1/ingest/sources/source-1/acquisitions",
        headers={"Idempotency-Key": "idem-1"},
        json={
            "rights_basis": "USER_PROVIDED",
            "rights_note": "本地合成测试素材",
        },
    )
    assert accepted.status_code == 202
    assert accepted.json()["job_type"] == "MEDIA_ACQUIRE"
