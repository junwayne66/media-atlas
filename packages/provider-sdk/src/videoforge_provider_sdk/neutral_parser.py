"""平台中性采集响应 → TrendItemSnapshot（docs/modules/40 §3.1）。平台无关。

输入是本仓库自有的归一化格式（非任何平台私有 API 结构），手工导入与 fixture
回放共用。缺失指标保留 null，绝不填 0（40 §3.2）。响应结构不符（如缺 item_id）
判为 Schema 漂移（SELECTOR_CHANGED），不静默丢弃。
"""

from datetime import UTC, datetime
from typing import Any

from videoforge_contracts import TrendItemSnapshot
from videoforge_contracts.ids import new_id
from videoforge_provider_sdk.connector_errors import ConnectorError
from videoforge_provider_sdk.discovery import ConnectorErrorCode

_METRICS = ("views", "likes", "comments", "shares", "saves")


class ParseError(ConnectorError):
    def __init__(self, detail: str) -> None:
        super().__init__(ConnectorErrorCode.SELECTOR_CHANGED, detail)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ParseError(f"非法时间格式: {value!r}") from exc


def _int_or_none(value: Any, field: str) -> int | None:
    if value is None:
        return None  # 未采到，保留 null（不填 0）
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ParseError(f"字段 {field} 应为数值或 null，实得 {value!r}")
    return int(value)


def parse_items(
    response: dict[str, Any],
    *,
    platform: str,
    collector_version: str,
    source_confidence: float,
    default_observed_at: datetime | None = None,
) -> list[TrendItemSnapshot]:
    if not isinstance(response, dict) or "items" not in response:
        raise ParseError("响应缺少 items 字段（结构漂移）")
    items = response["items"]
    if not isinstance(items, list):
        raise ParseError("items 必须是列表")

    observed_default = default_observed_at or datetime.now(UTC)
    snapshots: list[TrendItemSnapshot] = []
    for i, raw in enumerate(items):
        if not isinstance(raw, dict) or not raw.get("item_id"):
            raise ParseError(f"第 {i} 项缺少 item_id（结构漂移）")
        snapshots.append(
            TrendItemSnapshot(
                id=new_id(),
                observed_at=_parse_dt(raw.get("observed_at")) or observed_default,
                platform=platform,
                region=raw.get("region"),
                locale=raw.get("locale"),
                item_id=str(raw["item_id"]),
                author_id=raw.get("author_id"),
                published_at=_parse_dt(raw.get("published_at")),
                followers_at_observation=_int_or_none(raw.get("followers"), "followers"),
                rank=_int_or_none(raw.get("rank"), "rank"),
                hashtag_ids=list(raw.get("hashtags") or []),
                sound_id=raw.get("sound_id"),
                raw_artifact_id=raw.get("raw_artifact_id"),
                collector_version=collector_version,
                source_confidence=source_confidence,
                **{m: _int_or_none(raw.get(m), m) for m in _METRICS},
            )
        )
    return snapshots
