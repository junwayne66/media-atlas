import pytest
from trend_repo_factories import make_cluster, make_snapshot

from videoforge_contracts import TrendStage
from videoforge_persistence import (
    NotFoundError,
    TrendClusterRepository,
    TrendItemSnapshotRepository,
    VersionConflictError,
    session_scope,
)


def test_snapshot_add_and_list_by_ids(session) -> None:
    repo = TrendItemSnapshotRepository(session)
    s1 = make_snapshot(item_id="a")
    s2 = make_snapshot(item_id="b", saves=None)
    repo.add_many([s1, s2])
    session.flush()
    got = repo.list_by_ids([s1.id, s2.id])
    assert {g.item_id for g in got} == {"a", "b"}
    assert repo.get(s1.id) == s1
    assert repo.list_by_ids([]) == []


def test_cluster_create_get_roundtrip(session) -> None:
    repo = TrendClusterRepository(session)
    cluster = make_cluster(hot_score=0.7)
    repo.create(cluster)
    session.flush()
    assert repo.get(cluster.id) == cluster


def test_list_filters_and_orders_by_hot_score(migrated_engine) -> None:
    with session_scope(migrated_engine) as s:
        repo = TrendClusterRepository(s)
        repo.create(make_cluster(hot_score=0.3, stage=TrendStage.RISING, vertical="ai-tech"))
        repo.create(make_cluster(hot_score=0.9, stage=TrendStage.PEAK, vertical="ai-tech"))
        repo.create(make_cluster(hot_score=0.5, stage=TrendStage.RISING, vertical="gaming"))

    with session_scope(migrated_engine) as s:
        repo = TrendClusterRepository(s)
        top = repo.list()
        assert [c.hot_score for c in top] == [0.9, 0.5, 0.3]  # 热度降序
        rising_ai = repo.list(stage=TrendStage.RISING, vertical="ai-tech")
        assert [c.hot_score for c in rising_ai] == [0.3]


def test_optimistic_update_conflict(migrated_engine) -> None:
    cluster = make_cluster()
    with session_scope(migrated_engine) as s:
        TrendClusterRepository(s).create(cluster)

    with session_scope(migrated_engine) as s:
        c = TrendClusterRepository(s).get(cluster.id)
        TrendClusterRepository(s).update(
            c.model_copy(update={"title": "编辑1"}), expected_version=c.version
        )

    with pytest.raises(VersionConflictError):
        with session_scope(migrated_engine) as s:
            TrendClusterRepository(s).update(
                cluster.model_copy(update={"title": "编辑2"}), expected_version=cluster.version
            )


def test_merge_preserves_provenance_and_archives_source(migrated_engine) -> None:
    target = make_cluster(member_item_ids=["dy-1"], keywords=["AI"])
    source = make_cluster(member_item_ids=["tt-9"], keywords=["chip"])
    with session_scope(migrated_engine) as s:
        repo = TrendClusterRepository(s)
        repo.create(target)
        repo.create(source)

    with session_scope(migrated_engine) as s:
        repo = TrendClusterRepository(s)
        merged = repo.merge(
            target.id, source.id, expected_version=target.version, reason="同一事件"
        )
    assert set(merged.member_item_ids) == {"dy-1", "tt-9"}  # 成员并入，不丢
    assert set(merged.keywords) == {"AI", "chip"}
    assert f"MERGED_FROM:{source.id}" in merged.reason_codes

    with session_scope(migrated_engine) as s:
        archived = TrendClusterRepository(s).get(source.id)
    assert archived.stage == TrendStage.ARCHIVED  # source 归档非删除
    assert any(c.startswith(f"MERGED_INTO:{target.id}") for c in archived.reason_codes)


def test_split_moves_members_to_new_cluster(migrated_engine) -> None:
    original = make_cluster(member_item_ids=["a", "b", "c"])
    with session_scope(migrated_engine) as s:
        TrendClusterRepository(s).create(original)

    with session_scope(migrated_engine) as s:
        repo = TrendClusterRepository(s)
        kept, new = repo.split(
            original.id,
            ["b", "c"],
            expected_version=original.version,
            new_title="拆出的新热点",
            new_canonical_topic="ai-chip-variant",
        )
    assert kept.member_item_ids == ["a"]
    assert set(new.member_item_ids) == {"b", "c"}
    assert new.stage == TrendStage.EMERGING
    assert f"SPLIT_FROM:{original.id}" in new.reason_codes

    with session_scope(migrated_engine) as s:
        assert set(TrendClusterRepository(s).get(new.id).member_item_ids) == {"b", "c"}


def test_split_partitions_snapshots_by_item(migrated_engine) -> None:
    # 快照按 item_id 分派：被拆走成员的快照跟去新聚类，其余留原聚类
    s_a = make_snapshot(item_id="a")
    s_b = make_snapshot(item_id="b")
    original = make_cluster(member_item_ids=["a", "b"], snapshot_ids=[s_a.id, s_b.id])
    with session_scope(migrated_engine) as s:
        TrendItemSnapshotRepository(s).add_many([s_a, s_b])
        TrendClusterRepository(s).create(original)

    with session_scope(migrated_engine) as s:
        kept, new = TrendClusterRepository(s).split(
            original.id,
            ["b"],
            expected_version=original.version,
            new_title="拆 b",
            new_canonical_topic="b-topic",
        )
    assert kept.snapshot_ids == [s_a.id]  # a 的快照留原聚类
    assert new.snapshot_ids == [s_b.id]  # b 的快照跟去新聚类


def test_split_rejects_full_or_foreign_members(migrated_engine) -> None:
    original = make_cluster(member_item_ids=["a", "b"])
    with session_scope(migrated_engine) as s:
        TrendClusterRepository(s).create(original)
    with session_scope(migrated_engine) as s:
        repo = TrendClusterRepository(s)
        with pytest.raises(ValueError, match="全部成员"):
            repo.split(
                original.id,
                ["a", "b"],
                expected_version=original.version,
                new_title="x",
                new_canonical_topic="y",
            )
        with pytest.raises(ValueError, match="子集"):
            repo.split(
                original.id,
                ["z"],
                expected_version=original.version,
                new_title="x",
                new_canonical_topic="y",
            )


def test_get_missing_raises(session) -> None:
    with pytest.raises(NotFoundError):
        TrendClusterRepository(session).get("nope")
