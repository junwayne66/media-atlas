from datetime import UTC, datetime

from fastapi.testclient import TestClient

from videoforge_api.main import create_app
from videoforge_api.trends import (
    AttachSnapshotsRequest,
    CreateClusterRequest,
    CreateProjectRequest,
    MergeRequest,
    RescoreRequest,
    SplitRequest,
    SplitResponse,
)
from videoforge_contracts import Project, ProjectStatus, TrendCluster, TrendStage

_T0 = datetime(2026, 7, 22, tzinfo=UTC)


def _cluster(cid: str = "c1", **over) -> TrendCluster:
    values = dict(
        id=cid,
        title="AI 芯片热点",
        canonical_topic="ai-chip",
        member_item_ids=["dy-1", "tt-1"],
        first_seen_at=_T0,
        last_seen_at=_T0,
        stage=TrendStage.RISING,
        hot_score=0.7,
        source_confidence=0.85,
        vertical="ai-tech",
        created_at=_T0,
        updated_at=_T0,
    )
    values.update(over)
    return TrendCluster(**values)


class StubTrendGateway:
    def __init__(self) -> None:
        self.created_projects: list[tuple[str, CreateProjectRequest]] = []
        self.merges: list[tuple[str, MergeRequest]] = []

    def create_cluster(self, request: CreateClusterRequest) -> TrendCluster:
        return _cluster(title=request.title, canonical_topic=request.canonical_topic)

    def list_clusters(self, stage, vertical, limit) -> list[TrendCluster]:
        clusters = [_cluster("c1", hot_score=0.9), _cluster("c2", hot_score=0.5)]
        if stage is not None:
            clusters = [c for c in clusters if c.stage == stage]
        return clusters[:limit]

    def get_cluster(self, cluster_id: str) -> TrendCluster:
        if cluster_id == "missing":
            from videoforge_persistence import NotFoundError

            raise NotFoundError("trend_cluster", cluster_id)
        return _cluster(cluster_id)

    def attach_snapshots(self, cluster_id: str, request: AttachSnapshotsRequest) -> TrendCluster:
        return _cluster(cluster_id, version=request.expected_version + 1)

    def merge(self, cluster_id: str, request: MergeRequest) -> TrendCluster:
        self.merges.append((cluster_id, request))
        return _cluster(cluster_id, member_item_ids=["dy-1", "tt-1", "merged"])

    def split(self, cluster_id: str, request: SplitRequest) -> SplitResponse:
        return SplitResponse(
            original=_cluster(cluster_id, member_item_ids=["dy-1"]),
            created=_cluster("new", member_item_ids=request.member_item_ids),
        )

    def rescore(self, cluster_id: str, request: RescoreRequest) -> TrendCluster:
        return _cluster(cluster_id, hot_score=0.88, version=request.expected_version + 1)

    def create_project(self, cluster_id: str, request: CreateProjectRequest) -> Project:
        self.created_projects.append((cluster_id, request))
        return Project(
            id="p1",
            title=request.title or "auto",
            vertical="ai-tech",
            source_language=request.source_language,
            target_languages=request.target_languages,
            creation_mode=request.creation_mode,
            status=ProjectStatus.DRAFT,
            trend_cluster_id=cluster_id,
            created_at=_T0,
            updated_at=_T0,
        )


def _client() -> tuple[TestClient, StubTrendGateway]:
    app = create_app()
    stub = StubTrendGateway()
    app.state.trend_gateway = stub
    return TestClient(app), stub


def test_list_orders_and_filters() -> None:
    client, _ = _client()
    resp = client.get("/v1/trend-clusters")
    assert resp.status_code == 200
    body = resp.json()
    assert [c["hot_score"] for c in body] == [0.9, 0.5]
    assert client.get("/v1/trend-clusters?stage=RISING").status_code == 200
    assert client.get("/v1/trend-clusters?stage=PEAK").json() == []


def test_get_missing_404() -> None:
    client, _ = _client()
    assert client.get("/v1/trend-clusters/missing").status_code == 404
    assert client.get("/v1/trend-clusters/c1").json()["id"] == "c1"


def test_create_cluster() -> None:
    client, _ = _client()
    resp = client.post("/v1/trend-clusters", json={"title": "新热点", "canonical_topic": "topic"})
    assert resp.status_code == 201
    assert resp.json()["title"] == "新热点"


def test_merge_passes_through() -> None:
    client, stub = _client()
    resp = client.post(
        "/v1/trend-clusters/c1/merge",
        json={"source_id": "c2", "expected_version": 1, "reason": "同一事件"},
    )
    assert resp.status_code == 200
    assert "merged" in resp.json()["member_item_ids"]
    assert stub.merges[0][1].source_id == "c2"


def test_split_returns_both() -> None:
    client, _ = _client()
    resp = client.post(
        "/v1/trend-clusters/c1/split",
        json={
            "member_item_ids": ["tt-1"],
            "expected_version": 1,
            "new_title": "拆出",
            "new_canonical_topic": "t2",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["original"]["member_item_ids"] == ["dy-1"]
    assert body["created"]["member_item_ids"] == ["tt-1"]


def test_one_click_create_project() -> None:
    client, stub = _client()
    resp = client.post(
        "/v1/trend-clusters/c1/projects",
        json={
            "source_language": "zh-CN",
            "target_languages": ["en-US"],
            "creation_mode": "STRUCTURE_REWRITE",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["trend_cluster_id"] == "c1"
    assert body["creation_mode"] == "STRUCTURE_REWRITE"
    assert stub.created_projects[0][0] == "c1"


def test_create_project_validates_creation_mode() -> None:
    client, _ = _client()
    resp = client.post(
        "/v1/trend-clusters/c1/projects",
        json={"source_language": "zh-CN", "target_languages": ["en-US"], "creation_mode": "BOGUS"},
    )
    assert resp.status_code == 422


def test_rescore_and_attach() -> None:
    client, _ = _client()
    r1 = client.post("/v1/trend-clusters/c1/rescore", json={"expected_version": 1})
    assert r1.status_code == 200
    assert r1.json()["hot_score"] == 0.88
