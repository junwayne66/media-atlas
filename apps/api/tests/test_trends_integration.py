"""DbTrendGateway 真库端到端：create→attach→rescore→merge/split→建 Project。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, select

from videoforge_api.trends import (
    AttachSnapshotsRequest,
    CreateClusterRequest,
    CreateProjectRequest,
    DbTrendGateway,
    MergeRequest,
    RescoreRequest,
    SplitRequest,
)
from videoforge_contracts import CreationMode, TrendItemSnapshot, TrendStage
from videoforge_contracts.ids import new_id
from videoforge_persistence import session_scope
from videoforge_persistence.tables import OutboxEventRow

_T0 = datetime(2026, 7, 22, tzinfo=UTC)


def _snap(item: str, platform: str, hours: int, views: int) -> TrendItemSnapshot:
    return TrendItemSnapshot(
        id=new_id(),
        observed_at=_T0 + timedelta(hours=hours),
        platform=platform,
        item_id=item,
        collector_version="t@0",
        source_confidence=0.9,
        views=views,
        likes=views // 10,
    )


def test_attach_snapshots_rescore_and_create_project(migrated_engine: Engine) -> None:
    gw = DbTrendGateway(migrated_engine)
    cluster = gw.create_cluster(
        CreateClusterRequest(title="AI 芯片", canonical_topic="ai-chip", vertical="ai-tech")
    )
    assert cluster.stage == TrendStage.EMERGING
    assert cluster.hot_score is None

    snaps = [
        _snap("dy-1", "douyin", 0, 5000),
        _snap("dy-1", "douyin", 1, 25000),
        _snap("dy-1", "douyin", 2, 80000),
        _snap("tt-1", "tiktok", 0, 4000),
        _snap("tt-1", "tiktok", 2, 70000),
    ]
    rescored = gw.attach_snapshots(
        cluster.id, AttachSnapshotsRequest(expected_version=1, snapshots=snaps)
    )
    assert rescored.version == 2
    assert rescored.hot_score is not None and rescored.hot_score > 0
    assert rescored.sub_scores.cross_platform_score == 1.0  # 两平台
    assert set(rescored.member_item_ids) == {"dy-1", "tt-1"}
    assert len(rescored.snapshot_ids) == 5

    # 一键建 Project：带上 trend_cluster_id，同事务写 outbox
    project = gw.create_project(
        cluster.id,
        CreateProjectRequest(
            source_language="zh-CN",
            target_languages=["en-US"],
            creation_mode=CreationMode.STRUCTURE_REWRITE,
        ),
    )
    assert project.trend_cluster_id == cluster.id
    assert project.vertical == "ai-tech"
    with session_scope(migrated_engine) as s:
        event_types = [
            e.event_type
            for e in s.scalars(
                select(OutboxEventRow).where(OutboxEventRow.aggregate_id == project.id)
            )
        ]
    assert event_types == ["project.created"]


def test_rescore_is_replayable_through_gateway(migrated_engine: Engine) -> None:
    gw = DbTrendGateway(migrated_engine)
    cluster = gw.create_cluster(CreateClusterRequest(title="t", canonical_topic="topic"))
    snaps = [_snap("dy-1", "douyin", h, 1000 * (h + 1) ** 2) for h in range(4)]
    r1 = gw.attach_snapshots(
        cluster.id, AttachSnapshotsRequest(expected_version=1, snapshots=snaps)
    )
    r2 = gw.rescore(r1.id, RescoreRequest(expected_version=r1.version))
    r3 = gw.rescore(r2.id, RescoreRequest(expected_version=r2.version))
    # 同快照同权重 → 热度稳定（可重放）
    assert r2.hot_score == r3.hot_score
    assert r2.sub_scores == r3.sub_scores


def test_merge_and_split_through_gateway(migrated_engine: Engine) -> None:
    gw = DbTrendGateway(migrated_engine)
    target = gw.create_cluster(CreateClusterRequest(title="主", canonical_topic="a"))
    source = gw.create_cluster(CreateClusterRequest(title="副", canonical_topic="b"))
    gw.attach_snapshots(
        target.id,
        AttachSnapshotsRequest(expected_version=1, snapshots=[_snap("dy-1", "douyin", 0, 1000)]),
    )
    gw.attach_snapshots(
        source.id,
        AttachSnapshotsRequest(expected_version=1, snapshots=[_snap("tt-9", "tiktok", 0, 1000)]),
    )
    merged = gw.merge(
        target.id, MergeRequest(source_id=source.id, expected_version=2, reason="同事件")
    )
    assert set(merged.member_item_ids) == {"dy-1", "tt-9"}

    split = gw.split(
        merged.id,
        SplitRequest(
            member_item_ids=["tt-9"],
            expected_version=merged.version,
            new_title="拆出",
            new_canonical_topic="c",
        ),
    )
    assert split.original.member_item_ids == ["dy-1"]
    assert split.created.member_item_ids == ["tt-9"]
