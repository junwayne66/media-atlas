from fastapi.testclient import TestClient

from videoforge_api.main import create_app
from videoforge_api.operations import (
    OperationNotFound,
    OperationView,
    StartOperationRequest,
)


class StubOperationsService:
    def __init__(self) -> None:
        self.started: dict[str, StartOperationRequest] = {}
        self.reviews: list[tuple[str, str]] = []

    async def start(self, idempotency_key: str, request: StartOperationRequest) -> str:
        self.started[idempotency_key] = request
        return f"pipeline-{idempotency_key}"

    async def get(self, operation_id: str) -> OperationView:
        if operation_id == "missing":
            raise OperationNotFound(operation_id)
        return OperationView(
            operation_id=operation_id,
            running=True,
            stage="waiting_review",
            waiting_for_review=True,
        )

    async def review(self, operation_id: str, decision: str) -> None:
        if operation_id == "missing":
            raise OperationNotFound(operation_id)
        self.reviews.append((operation_id, decision))


def _client() -> tuple[TestClient, StubOperationsService]:
    app = create_app()
    stub = StubOperationsService()
    app.state.operations_service = stub
    return TestClient(app), stub


def test_start_requires_idempotency_key() -> None:
    client, _ = _client()
    resp = client.post("/v1/operations", json={"project_id": "p1", "title": "t"})
    assert resp.status_code == 422


def test_start_returns_operation_id() -> None:
    client, stub = _client()
    resp = client.post(
        "/v1/operations",
        json={"project_id": "p1", "title": "t"},
        headers={"Idempotency-Key": "k1"},
    )
    assert resp.status_code == 202
    assert resp.json() == {"operation_id": "pipeline-k1"}
    assert stub.started["k1"].project_id == "p1"


def test_get_operation_view() -> None:
    client, _ = _client()
    resp = client.get("/v1/operations/pipeline-k1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "waiting_review"
    assert body["waiting_for_review"] is True


def test_get_missing_returns_404() -> None:
    client, _ = _client()
    assert client.get("/v1/operations/missing").status_code == 404


def test_review_validates_decision() -> None:
    client, _ = _client()
    resp = client.post("/v1/operations/pipeline-k1/review", json={"decision": "ship-it"})
    assert resp.status_code == 422


def test_review_signals_service() -> None:
    client, stub = _client()
    resp = client.post("/v1/operations/pipeline-k1/review", json={"decision": "approve"})
    assert resp.status_code == 202
    assert stub.reviews == [("pipeline-k1", "approve")]
