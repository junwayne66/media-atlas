"""解析层：中性响应 → TrendItemSnapshot，null 保留，结构漂移可诊断。"""

import pytest
from fixtures_helper import load_fixture

from videoforge_connector_douyin import ParseError, parse_items


def _parse(name: str):
    return parse_items(
        load_fixture(name),
        platform="douyin",
        collector_version="douyin-collector@0.1.0",
        source_confidence=0.6,
    )


def test_parses_board_fixture_to_snapshots() -> None:
    snaps = _parse("board_response.json")
    assert [s.item_id for s in snaps] == ["dy-7412", "dy-7419"]
    top = snaps[0]
    assert top.views == 1200000
    assert top.rank == 1
    assert top.hashtag_ids == ["ai", "m5-chip"]
    assert top.platform == "douyin"
    assert top.source_confidence == 0.6


def test_missing_metric_stays_null_not_zero() -> None:
    snaps = _parse("board_response.json")
    assert snaps[0].saves is None  # 未采到，保留 null
    assert snaps[1].comments is None
    assert snaps[1].saves == 900  # 有值的照常


def test_empty_items_yields_no_snapshots() -> None:
    assert _parse("empty_response.json") == []


def test_structure_drift_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="item_id"):
        _parse("drift_response.json")


def test_missing_items_field_raises() -> None:
    with pytest.raises(ParseError, match="items"):
        parse_items(
            {"data": []},
            platform="douyin",
            collector_version="v",
            source_confidence=0.6,
        )


def test_non_numeric_metric_rejected() -> None:
    with pytest.raises(ParseError, match="views"):
        parse_items(
            {"items": [{"item_id": "x", "views": "many"}]},
            platform="douyin",
            collector_version="v",
            source_confidence=0.6,
        )
