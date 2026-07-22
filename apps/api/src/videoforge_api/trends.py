"""热点情报 API（docs/modules/40 §8）。

路由是 gateway 的薄封装；gateway 组合 persistence（cluster/snapshot/project repo）
与 domain（rescore_cluster）。人工拆分/合并走乐观锁，不被无条件覆盖（40 §10）。
"""

from datetime import UTC, datetime
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from videoforge_contracts import (
    CreationMode,
    HotScoreWeights,
    Project,
    ProjectStatus,
    TrendCluster,
    TrendItemSnapshot,
    TrendStage,
)
from videoforge_contracts.ids import new_id
from videoforge_domain import rescore_cluster
from videoforge_persistence import (
    NotFoundError,
    ProjectRepository,
    TrendClusterRepository,
    TrendItemSnapshotRepository,
    VersionConflictError,
    session_scope,
)


class CreateClusterRequest(BaseModel):
    title: str = Field(min_length=1)
    canonical_topic: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    vertical: str | None = None
    source_confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class AttachSnapshotsRequest(BaseModel):
    expected_version: int = Field(ge=1)
    snapshots: list[TrendItemSnapshot] = Field(min_length=1)


class MergeRequest(BaseModel):
    source_id: str = Field(min_length=1)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class SplitRequest(BaseModel):
    member_item_ids: list[str] = Field(min_length=1)
    expected_version: int = Field(ge=1)
    new_title: str = Field(min_length=1)
    new_canonical_topic: str = Field(min_length=1)


class RescoreRequest(BaseModel):
    expected_version: int = Field(ge=1)
    weights: HotScoreWeights | None = None


class CreateProjectRequest(BaseModel):
    title: str | None = None
    source_language: str = Field(min_length=2)
    target_languages: list[str] = Field(min_length=1)
    creation_mode: CreationMode


class SplitResponse(BaseModel):
    original: TrendCluster
    created: TrendCluster


class TrendGateway(Protocol):
    def create_cluster(self, request: CreateClusterRequest) -> TrendCluster: ...
    def list_clusters(
        self, stage: TrendStage | None, vertical: str | None, limit: int
    ) -> list[TrendCluster]: ...
    def get_cluster(self, cluster_id: str) -> TrendCluster: ...
    def attach_snapshots(
        self, cluster_id: str, request: AttachSnapshotsRequest
    ) -> TrendCluster: ...
    def merge(self, cluster_id: str, request: MergeRequest) -> TrendCluster: ...
    def split(self, cluster_id: str, request: SplitRequest) -> SplitResponse: ...
    def rescore(self, cluster_id: str, request: RescoreRequest) -> TrendCluster: ...
    def create_project(self, cluster_id: str, request: CreateProjectRequest) -> Project: ...


class DbTrendGateway:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_cluster(self, request: CreateClusterRequest) -> TrendCluster:
        now = datetime.now(UTC)
        cluster = TrendCluster(
            id=new_id(),
            title=request.title,
            canonical_topic=request.canonical_topic,
            keywords=request.keywords,
            entities=request.entities,
            first_seen_at=now,
            last_seen_at=now,
            stage=TrendStage.EMERGING,
            source_confidence=request.source_confidence,
            vertical=request.vertical,
            created_at=now,
            updated_at=now,
        )
        with session_scope(self._engine) as s:
            TrendClusterRepository(s).create(cluster)
        return cluster

    def list_clusters(
        self, stage: TrendStage | None, vertical: str | None, limit: int
    ) -> list[TrendCluster]:
        with session_scope(self._engine) as s:
            return TrendClusterRepository(s).list(stage=stage, vertical=vertical, limit=limit)

    def get_cluster(self, cluster_id: str) -> TrendCluster:
        with session_scope(self._engine) as s:
            return TrendClusterRepository(s).get(cluster_id)

    def attach_snapshots(self, cluster_id: str, request: AttachSnapshotsRequest) -> TrendCluster:
        with session_scope(self._engine) as s:
            snap_repo = TrendItemSnapshotRepository(s)
            snap_repo.add_many(request.snapshots)
            repo = TrendClusterRepository(s)
            cluster = repo.get(cluster_id)
            new_snapshot_ids = list(
                dict.fromkeys(cluster.snapshot_ids + [snap.id for snap in request.snapshots])
            )
            new_members = list(
                dict.fromkeys(
                    cluster.member_item_ids + [snap.item_id for snap in request.snapshots]
                )
            )
            all_snaps = snap_repo.list_by_ids(new_snapshot_ids)
            last_seen = max(
                [cluster.last_seen_at, *[snap.observed_at for snap in request.snapshots]]
            )
            withdata = cluster.model_copy(
                update={
                    "snapshot_ids": new_snapshot_ids,
                    "member_item_ids": new_members,
                    "last_seen_at": last_seen,
                }
            )
            rescored = rescore_cluster(withdata, all_snaps, HotScoreWeights())
            return repo.update(rescored, expected_version=request.expected_version)

    def merge(self, cluster_id: str, request: MergeRequest) -> TrendCluster:
        with session_scope(self._engine) as s:
            return TrendClusterRepository(s).merge(
                cluster_id,
                request.source_id,
                expected_version=request.expected_version,
                reason=request.reason,
            )

    def split(self, cluster_id: str, request: SplitRequest) -> SplitResponse:
        with session_scope(self._engine) as s:
            original, created = TrendClusterRepository(s).split(
                cluster_id,
                request.member_item_ids,
                expected_version=request.expected_version,
                new_title=request.new_title,
                new_canonical_topic=request.new_canonical_topic,
            )
        return SplitResponse(original=original, created=created)

    def rescore(self, cluster_id: str, request: RescoreRequest) -> TrendCluster:
        weights = request.weights or HotScoreWeights()
        with session_scope(self._engine) as s:
            repo = TrendClusterRepository(s)
            cluster = repo.get(cluster_id)
            snaps = TrendItemSnapshotRepository(s).list_by_ids(cluster.snapshot_ids)
            rescored = rescore_cluster(cluster, snaps, weights)
            return repo.update(rescored, expected_version=request.expected_version)

    def create_project(self, cluster_id: str, request: CreateProjectRequest) -> Project:
        now = datetime.now(UTC)
        with session_scope(self._engine) as s:
            cluster = TrendClusterRepository(s).get(cluster_id)
            project = Project(
                id=new_id(),
                title=request.title or f"{cluster.title}（二创）",
                vertical=cluster.vertical or "general",
                source_language=request.source_language,
                target_languages=request.target_languages,
                creation_mode=request.creation_mode,
                status=ProjectStatus.DRAFT,
                trend_cluster_id=cluster.id,
                created_at=now,
                updated_at=now,
            )
            ProjectRepository(s).create(project)  # 同事务写 outbox project.created
            return project


router = APIRouter(prefix="/v1/trend-clusters", tags=["trends"])


def get_trend_gateway(request: Request) -> TrendGateway:
    return request.app.state.trend_gateway


GatewayDep = Annotated[TrendGateway, Depends(get_trend_gateway)]


def _not_found(cluster_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"trend cluster 不存在: {cluster_id}")


def _conflict(exc: VersionConflictError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@router.post("", status_code=201)
def create_cluster(body: CreateClusterRequest, gateway: GatewayDep) -> TrendCluster:
    return gateway.create_cluster(body)


@router.get("")
def list_clusters(
    gateway: GatewayDep,
    stage: TrendStage | None = None,
    vertical: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[TrendCluster]:
    return gateway.list_clusters(stage, vertical, limit)


@router.get("/{cluster_id}")
def get_cluster(cluster_id: str, gateway: GatewayDep) -> TrendCluster:
    try:
        return gateway.get_cluster(cluster_id)
    except NotFoundError:
        raise _not_found(cluster_id) from None


@router.post("/{cluster_id}/snapshots")
def attach_snapshots(
    cluster_id: str, body: AttachSnapshotsRequest, gateway: GatewayDep
) -> TrendCluster:
    try:
        return gateway.attach_snapshots(cluster_id, body)
    except NotFoundError:
        raise _not_found(cluster_id) from None
    except VersionConflictError as exc:
        raise _conflict(exc) from None


@router.post("/{cluster_id}/merge")
def merge_cluster(cluster_id: str, body: MergeRequest, gateway: GatewayDep) -> TrendCluster:
    try:
        return gateway.merge(cluster_id, body)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except VersionConflictError as exc:
        raise _conflict(exc) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/{cluster_id}/split")
def split_cluster(cluster_id: str, body: SplitRequest, gateway: GatewayDep) -> SplitResponse:
    try:
        return gateway.split(cluster_id, body)
    except NotFoundError:
        raise _not_found(cluster_id) from None
    except VersionConflictError as exc:
        raise _conflict(exc) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.post("/{cluster_id}/rescore")
def rescore_cluster_endpoint(
    cluster_id: str, body: RescoreRequest, gateway: GatewayDep
) -> TrendCluster:
    try:
        return gateway.rescore(cluster_id, body)
    except NotFoundError:
        raise _not_found(cluster_id) from None
    except VersionConflictError as exc:
        raise _conflict(exc) from None


@router.post("/{cluster_id}/projects", status_code=201)
def create_project_from_cluster(
    cluster_id: str, body: CreateProjectRequest, gateway: GatewayDep
) -> Project:
    try:
        return gateway.create_project(cluster_id, body)
    except NotFoundError:
        raise _not_found(cluster_id) from None
