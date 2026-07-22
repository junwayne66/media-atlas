from datetime import UTC, datetime, timedelta

from videoforge_contracts import TrendCluster, TrendItemSnapshot, TrendStage
from videoforge_persistence import new_id

T0 = datetime(2026, 7, 22, 0, 0, 0, tzinfo=UTC)


def make_snapshot(**overrides) -> TrendItemSnapshot:
    values = {
        "id": new_id(),
        "observed_at": T0,
        "platform": "douyin",
        "item_id": "dy-1",
        "collector_version": "test@0",
        "source_confidence": 0.9,
        "views": 100000,
        "likes": 8000,
    }
    values.update(overrides)
    return TrendItemSnapshot(**values)


def make_cluster(**overrides) -> TrendCluster:
    values = {
        "id": new_id(),
        "title": "AI 芯片热点",
        "canonical_topic": "ai-chip",
        "keywords": ["AI", "芯片"],
        "member_item_ids": ["dy-1", "tt-1"],
        "snapshot_ids": [],
        "first_seen_at": T0,
        "last_seen_at": T0 + timedelta(hours=3),
        "stage": TrendStage.RISING,
        "source_confidence": 0.85,
        "vertical": "ai-tech",
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(overrides)
    return TrendCluster(**values)
