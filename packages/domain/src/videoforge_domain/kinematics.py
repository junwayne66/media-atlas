"""从快照时间序列计算热点动力学（docs/modules/40 §5 定义）。

纯函数、确定性、可重放（40 §10：给定快照得到完全相同结果）。原始增速/加速度
量纲无界，归一化到 [0,1] 子分数在 scoring.normalize_rate；此处只算原始物理量。
缺失指标的快照被跳过（40 §3.2：null 不当 0）。
"""

import math
from datetime import datetime

from videoforge_contracts import TrendItemSnapshot
from videoforge_domain.errors import InsufficientSnapshots

ENGAGEMENT_METRICS = ("likes", "comments", "shares", "saves")


def _points(snapshots: list[TrendItemSnapshot], metric: str) -> list[tuple[datetime, float]]:
    pts = [
        (s.observed_at, float(getattr(s, metric)))
        for s in snapshots
        if getattr(s, metric) is not None
    ]
    pts.sort(key=lambda p: p[0])
    return pts


def _hours(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0


def series_velocity(snapshots: list[TrendItemSnapshot], metric: str = "views") -> float:
    """最近一段的瞬时增速（每小时新增）。需 ≥2 个含该指标的快照。

    正值=还在增长；负值=已回落。
    """
    pts = _points(snapshots, metric)
    if len(pts) < 2:
        raise InsufficientSnapshots(f"velocity 需 ≥2 个含 {metric} 的快照，实得 {len(pts)}")
    (t0, v0), (t1, v1) = pts[-2], pts[-1]
    dt = _hours(t0, t1)
    if dt <= 0:
        raise InsufficientSnapshots("相邻快照时间差必须为正")
    return (v1 - v0) / dt


def series_acceleration(snapshots: list[TrendItemSnapshot], metric: str = "views") -> float:
    """增速的变化率（每小时²）。需 ≥3 点。正=正在起飞，负=正在减速。"""
    pts = _points(snapshots, metric)
    if len(pts) < 3:
        raise InsufficientSnapshots(f"acceleration 需 ≥3 个含 {metric} 的快照，实得 {len(pts)}")
    (t0, v0), (t1, v1), (t2, v2) = pts[-3], pts[-2], pts[-1]
    dt01 = _hours(t0, t1)
    dt12 = _hours(t1, t2)
    if dt01 <= 0 or dt12 <= 0:
        raise InsufficientSnapshots("相邻快照时间差必须为正")
    vel_prev = (v1 - v0) / dt01
    vel_last = (v2 - v1) / dt12
    return (vel_last - vel_prev) / dt12


def engagement_efficiency(snapshot: TrendItemSnapshot) -> float:
    """互动/观看，按账号体量校正到 [0,1]（40 §5）。

    views 缺失或为 0 → 0。粉丝越多、同等互动率含金量越低（大号自然到达便宜），
    用 followers 的对数轻微下调，小号基本不惩罚。
    """
    if not snapshot.views:  # None 或 0
        return 0.0
    total = sum(getattr(snapshot, m) or 0 for m in ENGAGEMENT_METRICS)
    rate = total / snapshot.views
    followers = snapshot.followers_at_observation
    if followers and followers > 0:
        size_factor = 1.0 / (1.0 + math.log10(followers / 1000.0 + 1.0))
        rate *= size_factor
    return max(0.0, min(1.0, rate))


def decline_from_peak(snapshots: list[TrendItemSnapshot], metric: str = "views") -> float:
    """从峰值回落的比例 [0,1]，作为 decay 子分数（40 §9：距峰值+速度转负）。

    仍在峰值/上升 → 0；已从峰值跌去一半 → 0.5。单调、可重放。
    """
    pts = _points(snapshots, metric)
    if len(pts) < 2:
        return 0.0
    values = [v for _, v in pts]
    peak = max(values)
    if peak <= 0:
        return 0.0
    last = values[-1]
    return max(0.0, min(1.0, (peak - last) / peak))
