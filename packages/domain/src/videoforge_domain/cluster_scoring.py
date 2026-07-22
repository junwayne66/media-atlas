"""聚类级重打分：从成员快照序列算出 TrendCluster 的子分数/热度/阶段/reason codes。

纯函数（合同进、合同出，无 I/O），可重放（40 §10）。把跨 item 的快照按观测时刻
聚合成总量序列，再套 VF-101 的动力学；跨平台数、来源可信度由快照直接得。归一化
用固定参考量纲（scale），真实 cohort robust z-score 校准待 VF-604。
"""

from collections import defaultdict
from datetime import datetime

from videoforge_contracts import (
    HotScoreWeights,
    TrendCluster,
    TrendItemSnapshot,
    TrendSubScores,
)
from videoforge_domain.kinematics import (
    decline_from_peak,
    engagement_efficiency,
    series_acceleration,
    series_velocity,
)
from videoforge_domain.reason_codes import derive_reason_codes
from videoforge_domain.scoring import hot_score, normalize_rate
from videoforge_domain.staging import classify_stage

# 参考量纲（views/小时）：约 1e4/h 的净增速映射到接近 1 的 velocity 子分数
_VELOCITY_SCALE = 10_000.0
_ACCELERATION_SCALE = 5_000.0


def _aggregate_series(snapshots: list[TrendItemSnapshot]) -> list[TrendItemSnapshot]:
    """把同一观测时刻、跨 item 的快照聚合为一个总量伪快照，形成聚类总热度序列。"""
    buckets: dict[datetime, list[TrendItemSnapshot]] = defaultdict(list)
    for s in snapshots:
        buckets[s.observed_at].append(s)

    aggregated: list[TrendItemSnapshot] = []
    for observed_at in sorted(buckets):
        group = buckets[observed_at]
        total_views = sum(s.views or 0 for s in group)
        total_eng = sum(
            (s.likes or 0) + (s.comments or 0) + (s.shares or 0) + (s.saves or 0) for s in group
        )
        aggregated.append(
            TrendItemSnapshot(
                id=group[0].id,
                observed_at=observed_at,
                platform="_aggregate",
                item_id="_cluster_total",
                collector_version="cluster-aggregate@1",
                source_confidence=1.0,
                views=total_views,
                likes=total_eng,  # 聚合互动放 likes 位，供 engagement_efficiency 用
            )
        )
    return aggregated


def compute_sub_scores(
    snapshots: list[TrendItemSnapshot],
    *,
    base: TrendSubScores | None = None,
) -> TrendSubScores:
    """从快照序列算可导出的子分数（velocity/acceleration/engagement/decay/cross_platform）；
    其余上下文子分数（topic_fit/novelty/source_quality/saturation）沿用 base 或默认 0。"""
    agg = _aggregate_series(snapshots)
    velocity = acceleration = 0.0
    decay = 0.0
    engagement = 0.0
    if len(agg) >= 2:
        velocity = normalize_rate(series_velocity(agg, "views"), scale=_VELOCITY_SCALE)
        decay = decline_from_peak(agg, "views")
        engagement = engagement_efficiency(agg[-1])
    if len(agg) >= 3:
        acceleration = normalize_rate(series_acceleration(agg, "views"), scale=_ACCELERATION_SCALE)
    platforms = {s.platform for s in snapshots}
    cross_platform = min(1.0, max(0, len(platforms) - 1) / 1.0)  # 2+ 平台 → 1.0

    ctx = base or TrendSubScores(velocity=0.0, acceleration=0.0, engagement_efficiency=0.0)
    return TrendSubScores(
        velocity=velocity,
        acceleration=acceleration,
        engagement_efficiency=engagement,
        cross_platform_score=cross_platform,
        topic_fit=ctx.topic_fit,
        novelty=ctx.novelty,
        source_quality=ctx.source_quality,
        saturation=ctx.saturation,
        decay=decay,
    )


def rescore_cluster(
    cluster: TrendCluster,
    snapshots: list[TrendItemSnapshot],
    weights: HotScoreWeights,
) -> TrendCluster:
    """用成员快照重算子分数/热度/阶段/reason codes，返回更新后的聚类合同。"""
    sub_scores = compute_sub_scores(snapshots, base=cluster.sub_scores)
    score = hot_score(sub_scores, weights, source_confidence=cluster.source_confidence)
    stage = classify_stage(sub_scores, sample_count=len(cluster.member_item_ids))
    # 保留人工合并/拆分留下的 provenance 码，叠加本次派生码
    provenance = [c for c in cluster.reason_codes if c.startswith(("MERGED_", "SPLIT_"))]
    reason_codes = provenance + [
        c for c in derive_reason_codes(sub_scores, stage) if c not in provenance
    ]
    return cluster.model_copy(
        update={
            "sub_scores": sub_scores,
            "hot_score": round(score, 6),
            "weights_version": weights.template_version,
            "stage": stage,
            "reason_codes": reason_codes,
        }
    )


__all__ = ["compute_sub_scores", "rescore_cluster"]
