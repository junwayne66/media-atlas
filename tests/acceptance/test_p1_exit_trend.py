"""P1 Exit 验收（热点）：Top-20 每条有证据且得分逐位可重放。

53 §P1 Exit：「热点 Top-20 有证据和可重放得分」。54 §2 热点行：多周期跨平台快照 →
运行评分 → 速度/加速度/阶段可重放且有理由。用纯 domain rescore_cluster（无 I/O）证明。
"""

from datetime import UTC, datetime, timedelta

from videoforge_contracts import HotScoreWeights, TrendCluster, TrendItemSnapshot, TrendStage
from videoforge_domain import rescore_cluster

_T0 = datetime(2026, 7, 22, tzinfo=UTC)
_WEIGHTS = HotScoreWeights()
_N_CLUSTERS = 24  # ≥20，取 Top-20


def _snap(item: str, platform: str, hours: int, views: int, likes: int) -> TrendItemSnapshot:
    return TrendItemSnapshot(
        id=f"{item}-{platform}-{hours}",
        observed_at=_T0 + timedelta(hours=hours),
        platform=platform,
        item_id=item,
        collector_version="acc@0",
        source_confidence=0.9,
        views=views,
        likes=likes,
    )


def _cluster(idx: int) -> tuple[TrendCluster, list[TrendItemSnapshot]]:
    # 跨平台多周期快照；增速随 idx 变化（150/簇，落在评分敏感区非饱和），Top-N 分数各不同
    growth = 150 * (idx + 1)
    snaps = [
        _snap(f"dy-{idx}", "douyin", 0, 1000, 80),
        _snap(f"dy-{idx}", "douyin", 1, 1000 + growth, 80 + growth // 10),
        _snap(f"dy-{idx}", "douyin", 2, 1000 + 3 * growth, 80 + 3 * growth // 10),
        _snap(f"tt-{idx}", "tiktok", 0, 800, 60),
        _snap(f"tt-{idx}", "tiktok", 2, 800 + 2 * growth, 60 + 2 * growth // 10),
    ]
    cluster = TrendCluster(
        id=f"c-{idx}",
        title=f"AI 热点 {idx}",
        canonical_topic=f"topic-{idx}",
        member_item_ids=[f"dy-{idx}", f"tt-{idx}"],
        snapshot_ids=[s.id for s in snaps],
        first_seen_at=_T0,
        last_seen_at=_T0 + timedelta(hours=2),
        stage=TrendStage.EMERGING,
        source_confidence=0.9,
        vertical="ai_tech",
        created_at=_T0,
        updated_at=_T0,
    )
    return cluster, snaps


def _all_rescored() -> list[TrendCluster]:
    scored = [rescore_cluster(c, s, _WEIGHTS) for c, s in (_cluster(i) for i in range(_N_CLUSTERS))]
    # 热度降序，None 垫底
    return sorted(scored, key=lambda c: (c.hot_score is not None, c.hot_score or 0.0), reverse=True)


def test_at_least_20_clusters_scored() -> None:
    assert len(_all_rescored()) >= 20


def test_top20_each_has_score_and_evidence() -> None:
    top20 = _all_rescored()[:20]
    assert len(top20) == 20
    for c in top20:
        assert c.hot_score is not None and 0.0 <= c.hot_score <= 1.0  # 有分
        assert c.sub_scores is not None  # 子分数（速度/加速度/跨平台等证据）
        assert len(c.reason_codes) >= 1  # 有理由（可解释）
        assert c.weights_version == "v1"  # 模板版本可追溯


def test_scores_are_replayable_to_the_bit() -> None:
    for i in range(_N_CLUSTERS):
        cluster, snaps = _cluster(i)
        a = rescore_cluster(cluster, snaps, _WEIGHTS)
        b = rescore_cluster(cluster, snaps, _WEIGHTS)
        assert a.hot_score == b.hot_score
        assert a.sub_scores == b.sub_scores
        assert a.stage == b.stage
        assert a.reason_codes == b.reason_codes


def test_top20_ordering_is_monotonic_and_differentiated() -> None:
    scores = [c.hot_score for c in _all_rescored()[:20]]
    assert scores == sorted(scores, reverse=True)  # 降序
    assert len(set(scores)) == 20  # 20 条分数各不同——Top-N 是真实排序而非并列
