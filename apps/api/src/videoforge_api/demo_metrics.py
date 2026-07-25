"""指标 Demo 录制（包资源）：驱动 `FakeMetricsConnector` 的回放数据。

**这不是真实平台数据**：真实平台官方数据 API 回采需真实账号 + 应用审核 + 凭据（stop-condition）。
录制里**刻意留了 null 指标**（saves / impressions / watch_time…）——§10 的 null 语义要在 API
响应里看得见：缺失就是 null，绝不填 0。

数据是随包分发的 JSON（`demo_recordings/metrics_demo.json`），经 `importlib.resources` 读取。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from functools import cache
from importlib import resources
from typing import Any

from videoforge_contracts import MetricField, PerformanceSnapshot, PublishPlatform
from videoforge_provider_sdk.metrics_connector import FakeMetricsConnector

DEMO_ACCOUNT_ID = "demo-account"
# 录制基准时刻：快照的 observed_at 由 published_at + age 推得，保证确定性（无时钟依赖）。
DEMO_PUBLISHED_AT = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)

# 录制里实际提供的指标（连接器如实上报能力——让 null 是"源本就不提供"的有据缺失）
DEMO_PROVIDED_FIELDS: tuple[MetricField, ...] = (
    MetricField.VIEWS,
    MetricField.LIKES,
    MetricField.COMMENTS,
    MetricField.SHARES,
    MetricField.FOLLOWS,
    MetricField.IMPRESSIONS,
    MetricField.WATCH_TIME,
    MetricField.AVG_WATCH_TIME,
    MetricField.COMPLETION_RATE,
)


def _load() -> Any:
    text = (
        resources.files("videoforge_api.demo_recordings")
        .joinpath("metrics_demo.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


@cache
def demo_recordings(
    platform: PublishPlatform,
) -> dict[tuple[str, float], PerformanceSnapshot]:
    """(post_id, age_hours) → 快照。null 字段保持 null（不补 0）。"""
    data = _load()
    account_id = data["account_id"]
    recorded: dict[tuple[str, float], PerformanceSnapshot] = {}
    for post in data["posts"]:
        post_id = post["platform_post_id"]
        for entry in post["snapshots"]:
            age = float(entry["age_hours"])
            fields = {k: v for k, v in entry.items() if k != "age_hours"}
            snapshot = PerformanceSnapshot(
                id=f"snap-{platform.value.lower()}-{post_id}-{age:g}",
                platform=platform,
                platform_post_id=post_id,
                account_id=account_id,
                observed_at=DEMO_PUBLISHED_AT + timedelta(hours=age),
                age_hours=age,
                **fields,
            )
            recorded[(post_id, age)] = snapshot
    return recorded


def default_metrics_connectors() -> dict[PublishPlatform, FakeMetricsConnector]:
    """默认指标连接器：Fake（零网络）。真实回采属 stop-condition。"""
    return {
        platform: FakeMetricsConnector(
            platform=platform,
            recorded=demo_recordings(platform),
            provided_fields=DEMO_PROVIDED_FIELDS,
        )
        for platform in (PublishPlatform.TIKTOK, PublishPlatform.DOUYIN)
    }


__all__ = [
    "DEMO_ACCOUNT_ID",
    "DEMO_PROVIDED_FIELDS",
    "DEMO_PUBLISHED_AT",
    "default_metrics_connectors",
    "demo_recordings",
]
