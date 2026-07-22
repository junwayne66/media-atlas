"""聚类重打分：从成员快照算子分数/热度/阶段/reason codes，可重放，保留 provenance。"""

from datetime import UTC, datetime, timedelta

from videoforge_contracts import (
    HotScoreWeights,
    TrendCluster,
    TrendItemSnapshot,
    TrendStage,
    TrendSubScores,
)
from videoforge_domain import compute_sub_scores, rescore_cluster

_T0 = datetime(2026, 7, 22, tzinfo=UTC)


def _snap(item, platform, hours, views, likes=0) -> TrendItemSnapshot:
    return TrendItemSnapshot(
        id=f"{item}-{hours}",
        observed_at=_T0 + timedelta(hours=hours),
        platform=platform,
        item_id=item,
        collector_version="t@0",
        source_confidence=0.9,
        views=views,
        likes=likes,
    )


def _cluster(**over) -> TrendCluster:
    values = dict(
        id="c1",
        title="t",
        canonical_topic="topic",
        member_item_ids=["dy-1", "tt-1"],
        first_seen_at=_T0,
        last_seen_at=_T0 + timedelta(hours=3),
        stage=TrendStage.EMERGING,
        source_confidence=0.9,
        created_at=_T0,
        updated_at=_T0,
    )
    values.update(over)
    return TrendCluster(**values)


def test_rising_cluster_scores_high_velocity_and_cross_platform() -> None:
    snaps = [
        _snap("dy-1", "douyin", 0, 5000, 400),
        _snap("dy-1", "douyin", 1, 20000, 1500),
        _snap("dy-1", "douyin", 2, 60000, 5000),
        _snap("tt-1", "tiktok", 0, 3000, 200),
        _snap("tt-1", "tiktok", 1, 15000, 1200),
        _snap("tt-1", "tiktok", 2, 50000, 4000),
    ]
    sub = compute_sub_scores(snaps)
    assert sub.velocity > 0.5  # 快速增长
    assert sub.acceleration > 0.0
    assert sub.cross_platform_score == 1.0  # 两个平台
    assert sub.decay == 0.0  # 还在涨


def test_rescore_is_replayable() -> None:
    snaps = [_snap("dy-1", "douyin", h, 1000 * (h + 1) ** 2) for h in range(4)]
    cluster = _cluster()
    weights = HotScoreWeights()
    a = rescore_cluster(cluster, snaps, weights)
    b = rescore_cluster(cluster, snaps, weights)
    assert a.hot_score == b.hot_score
    assert a.sub_scores == b.sub_scores
    assert a.stage == b.stage
    assert a.weights_version == "v1"


def test_rescore_derives_stage_and_reason_codes() -> None:
    snaps = [
        _snap("dy-1", "douyin", 0, 5000, 400),
        _snap("dy-1", "douyin", 1, 30000, 2500),
        _snap("dy-1", "douyin", 2, 90000, 8000),
        _snap("tt-1", "tiktok", 0, 4000, 300),
        _snap("tt-1", "tiktok", 2, 80000, 7000),
    ]
    result = rescore_cluster(_cluster(), snaps, HotScoreWeights())
    assert result.hot_score is not None and 0.0 <= result.hot_score <= 1.0
    assert result.stage in TrendStage
    assert len(result.reason_codes) >= 1


def test_rescore_preserves_merge_split_provenance() -> None:
    cluster = _cluster(reason_codes=["MERGED_FROM:c2", "OLD_DERIVED"])
    snaps = [_snap("dy-1", "douyin", h, 1000 * (h + 1)) for h in range(3)]
    result = rescore_cluster(cluster, snaps, HotScoreWeights())
    # 人工合并 provenance 保留，旧派生码被刷新
    assert "MERGED_FROM:c2" in result.reason_codes
    assert "OLD_DERIVED" not in result.reason_codes


def test_rescore_keeps_context_subscores_from_base() -> None:
    base = TrendSubScores(
        velocity=0.0, acceleration=0.0, engagement_efficiency=0.0, topic_fit=0.9, novelty=0.8
    )
    cluster = _cluster(sub_scores=base)
    snaps = [_snap("dy-1", "douyin", h, 1000 * (h + 1)) for h in range(3)]
    result = rescore_cluster(cluster, snaps, HotScoreWeights())
    assert result.sub_scores.topic_fit == 0.9  # 上下文子分数沿用
    assert result.sub_scores.novelty == 0.8


def test_sparse_snapshots_do_not_crash() -> None:
    # 单快照不足以算速度/加速度，应给 0 而非报错
    sub = compute_sub_scores([_snap("dy-1", "douyin", 0, 1000)])
    assert sub.velocity == 0.0
    assert sub.acceleration == 0.0
