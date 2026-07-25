from datetime import UTC, datetime

from fastapi.testclient import TestClient

from videoforge_api.main import create_app
from videoforge_api.workers import ClaimRequest, EnqueueRequest, RegisterRequest
from videoforge_contracts import TaskEnvelope
from videoforge_persistence import LeaseLostError, NotFoundError, TaskStateError


class StubGateway:
    def register(self, request: RegisterRequest) -> str:
        return "w-1"

    def heartbeat(self, worker_id: str) -> None:
        if worker_id == "ghost":
            raise NotFoundError("worker", worker_id)

    def enqueue(self, request: EnqueueRequest) -> str:
        return "t-1"

    def claim(self, request: ClaimRequest) -> TaskEnvelope | None:
        if request.capabilities == ["empty.queue"]:
            return None
        return TaskEnvelope(
            task_id="t-1",
            idempotency_key="k",
            capability=request.capabilities[0],
            attempt=1,
            lease_id="l-1",
            created_at=datetime.now(UTC),
        )

    def renew(self, task_id: str, request) -> datetime:
        if request.lease_id == "stale":
            raise LeaseLostError("租约已失效")
        return datetime.now(UTC)

    def complete(self, task_id: str, request) -> bool:
        return True

    def fail(self, task_id: str, request) -> None:
        return None

    def requeue(self, task_id: str, request) -> None:
        if task_id == "ghost":
            raise NotFoundError("worker_task", task_id)
        if task_id == "running":
            raise TaskStateError("task running 状态为 LEASED，只有 FAILED 可 requeue")

    def task_status(self, task_id: str) -> dict:
        raise NotFoundError("worker_task", task_id)


def _client() -> TestClient:
    app = create_app()
    app.state.worker_gateway = StubGateway()
    return TestClient(app)


def test_register_returns_worker_id() -> None:
    resp = _client().post(
        "/v1/workers/register",
        json={
            "name": "w",
            "hostname": "h",
            "os": "darwin",
            "arch": "arm64",
            "capabilities": ["a"],
            "execution_location": "local",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"worker_id": "w-1"}


def test_heartbeat_unknown_worker_404() -> None:
    client = _client()
    assert client.post("/v1/workers/w-1/heartbeat").status_code == 204
    assert client.post("/v1/workers/ghost/heartbeat").status_code == 404


def test_claim_returns_envelope_or_204() -> None:
    client = _client()
    hit = client.post(
        "/v1/worker-tasks/claim", json={"worker_id": "w-1", "capabilities": ["source.discover"]}
    )
    assert hit.status_code == 200
    assert hit.json()["task_id"] == "t-1"
    miss = client.post(
        "/v1/worker-tasks/claim", json={"worker_id": "w-1", "capabilities": ["empty.queue"]}
    )
    assert miss.status_code == 204


def test_renew_stale_lease_409() -> None:
    resp = _client().post("/v1/worker-tasks/t-1/renew", json={"lease_id": "stale"})
    assert resp.status_code == 409


def test_status_missing_404_and_enqueue_202() -> None:
    client = _client()
    assert client.get("/v1/worker-tasks/nope").status_code == 404
    resp = client.post(
        "/v1/worker-tasks",
        json={"capability": "source.discover", "idempotency_key": "k1"},
    )
    assert resp.status_code == 202
    assert resp.json() == {"task_id": "t-1"}


def test_requeue_failed_task_204_and_error_mapping() -> None:
    client = _client()
    assert client.post("/v1/worker-tasks/t-1/requeue", json={}).status_code == 204
    assert client.post("/v1/worker-tasks/t-1/requeue", json={"max_attempts": 3}).status_code == 204
    assert client.post("/v1/worker-tasks/ghost/requeue", json={}).status_code == 404
    # 非 FAILED 任务不可重排 → 409
    assert client.post("/v1/worker-tasks/running/requeue", json={}).status_code == 409
    # 上限必须 ≥ 1
    assert client.post("/v1/worker-tasks/t-1/requeue", json={"max_attempts": 0}).status_code == 422
