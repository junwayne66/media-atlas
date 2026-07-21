"""hot_score 聚合与可重放性（VF-101 DoD：给定快照+权重得完全相同结果）。"""

import math

import pytest
from pydantic import ValidationError

from videoforge_contracts import HotScoreWeights, TrendSubScores
from videoforge_domain import hot_score, normalize_rate, sigmoid


def test_negative_weight_rejected() -> None:
    # 权重是幅值；负向由公式承载，坏模板应被挡下
    with pytest.raises(ValidationError):
        HotScoreWeights(velocity=-0.5)


def _subs(**over) -> TrendSubScores:
    base = dict(velocity=0.0, acceleration=0.0, engagement_efficiency=0.0)
    base.update(over)
    return TrendSubScores(**base)


def test_hot_score_matches_hand_computation() -> None:
    weights = HotScoreWeights()  # 文档默认
    sub = TrendSubScores(
        velocity=0.8,
        acceleration=0.6,
        engagement_efficiency=0.4,
        cross_platform_score=0.7,
        topic_fit=0.9,
        novelty=0.5,
        source_quality=0.6,
        saturation=0.3,
        decay=0.1,
    )
    raw = (
        0.24 * 0.8
        + 0.18 * 0.6
        + 0.14 * 0.4
        + 0.13 * 0.7
        + 0.12 * 0.9
        + 0.10 * 0.5
        + 0.09 * 0.6
        - 0.15 * 0.3
        - 0.12 * 0.1
    )
    expected = (1 / (1 + math.exp(-raw))) * 0.9
    assert hot_score(sub, weights, source_confidence=0.9) == pytest.approx(expected)


def test_hot_score_is_replayable() -> None:
    weights = HotScoreWeights()
    sub = _subs(velocity=0.5, acceleration=0.3)
    a = hot_score(sub, weights, source_confidence=0.8)
    b = hot_score(sub, weights, source_confidence=0.8)
    assert a == b  # 位级相同，可重放


def test_saturation_and_decay_lower_score() -> None:
    weights = HotScoreWeights()
    hot = _subs(velocity=0.7, acceleration=0.5)
    saturated = _subs(velocity=0.7, acceleration=0.5, saturation=0.9, decay=0.8)
    assert hot_score(saturated, weights, source_confidence=1.0) < hot_score(
        hot, weights, source_confidence=1.0
    )


def test_source_confidence_scales_score() -> None:
    weights = HotScoreWeights()
    sub = _subs(velocity=0.6, acceleration=0.4)
    full = hot_score(sub, weights, source_confidence=1.0)
    half = hot_score(sub, weights, source_confidence=0.5)
    assert half == pytest.approx(full * 0.5)


def test_custom_weight_template_changes_result() -> None:
    sub = _subs(velocity=0.9, acceleration=0.1)
    default = hot_score(sub, HotScoreWeights(), source_confidence=1.0)
    velocity_heavy = hot_score(
        sub, HotScoreWeights(template_version="v2", velocity=0.5), source_confidence=1.0
    )
    assert velocity_heavy > default  # 权重是模板参数，不写死


def test_normalize_rate_monotonic_and_bounded() -> None:
    assert normalize_rate(-10, scale=100) == 0.0  # 下降不计入正向 velocity
    assert normalize_rate(0, scale=100) == 0.0
    small = normalize_rate(50, scale=100)
    big = normalize_rate(500, scale=100)
    assert 0.0 < small < big < 1.0
    assert sigmoid(0.0) == pytest.approx(0.5)
