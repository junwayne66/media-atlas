import pytest
from fastapi.testclient import TestClient

from videoforge_api.main import create_app
from videoforge_api.readiness import IngestReadiness

pytestmark = pytest.mark.no_db


class StubReadiness:
    def inspect(self) -> IngestReadiness:
        return IngestReadiness(
            status="ready",
            database="ready",
            object_store="ready",
            pending_tasks=3,
            stale_leases=1,
            parser_errors_24h=2,
            challenges_24h=4,
        )


def test_ingest_readiness_is_structured() -> None:
    app = create_app()
    app.state.ingest_readiness_gateway = StubReadiness()
    response = TestClient(app).get("/v1/ingest/readiness")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ready",
        "object_store": "ready",
        "pending_tasks": 3,
        "stale_leases": 1,
        "parser_errors_24h": 2,
        "challenges_24h": 4,
    }
