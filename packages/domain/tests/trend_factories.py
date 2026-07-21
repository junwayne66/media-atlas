from datetime import UTC, datetime, timedelta

from videoforge_contracts import TrendItemSnapshot

_T0 = datetime(2026, 7, 22, 0, 0, 0, tzinfo=UTC)


def snapshot_series(
    values: list[int | None],
    *,
    metric: str = "views",
    step_hours: float = 1.0,
    platform: str = "douyin",
) -> list[TrendItemSnapshot]:
    """按小时步长构造一串快照，只填指定 metric（其余留 null）。"""
    series = []
    for i, v in enumerate(values):
        series.append(
            TrendItemSnapshot(
                id=f"snap-{i}",
                observed_at=_T0 + timedelta(hours=step_hours * i),
                platform=platform,
                item_id="item-1",
                collector_version="test@0",
                source_confidence=1.0,
                **{metric: v},
            )
        )
    return series
