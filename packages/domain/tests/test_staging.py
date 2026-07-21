"""趋势阶段分类与合法迁移（docs/modules/40 §6）。"""

import pytest

from videoforge_contracts import TrendStage, TrendSubScores
from videoforge_domain import (
    STAGE_TRANSITIONS,
    IllegalStageTransition,
    assert_transition,
    can_transition,
    classify_stage,
)


def _subs(**over) -> TrendSubScores:
    base = dict(velocity=0.0, acceleration=0.0, engagement_efficiency=0.0)
    base.update(over)
    return TrendSubScores(**base)


def test_emerging_when_few_samples_high_acceleration() -> None:
    stage = classify_stage(_subs(velocity=0.2, acceleration=0.8), sample_count=2)
    assert stage == TrendStage.EMERGING


def test_rising_when_velocity_grows() -> None:
    stage = classify_stage(_subs(velocity=0.5, acceleration=0.3), sample_count=20)
    assert stage == TrendStage.RISING


def test_peak_when_high_velocity_low_acceleration() -> None:
    stage = classify_stage(_subs(velocity=0.8, acceleration=0.05), sample_count=50)
    assert stage == TrendStage.PEAK


def test_saturated_when_supply_high() -> None:
    stage = classify_stage(_subs(velocity=0.5, acceleration=0.1, saturation=0.7), sample_count=50)
    assert stage == TrendStage.SATURATED


def test_decaying_when_declined() -> None:
    stage = classify_stage(_subs(velocity=0.05, acceleration=0.0, decay=0.6), sample_count=50)
    assert stage == TrendStage.DECAYING


def test_legal_forward_transitions() -> None:
    assert can_transition(TrendStage.EMERGING, TrendStage.RISING)
    assert can_transition(TrendStage.RISING, TrendStage.PEAK)
    assert can_transition(TrendStage.DECAYING, TrendStage.RISING)  # 二次起飞
    assert_transition(TrendStage.RISING, TrendStage.PEAK)


def test_forward_skips_allowed_for_infrequent_observation() -> None:
    # 观测间隔大时可跨级：classify_stage 的任意输出都能从更早阶段合法到达
    assert can_transition(TrendStage.EMERGING, TrendStage.PEAK)
    assert can_transition(TrendStage.EMERGING, TrendStage.SATURATED)
    assert can_transition(TrendStage.RISING, TrendStage.DECAYING)


def test_classifier_output_is_always_reachable_from_emerging() -> None:
    # 分类器与迁移表的接缝：EMERGING 起步的簇能迁到任何分类结果（除倒退）
    for target in (TrendStage.RISING, TrendStage.PEAK, TrendStage.SATURATED, TrendStage.DECAYING):
        assert can_transition(TrendStage.EMERGING, target)


def test_illegal_transitions_rejected() -> None:
    assert not can_transition(TrendStage.PEAK, TrendStage.EMERGING)  # 不能倒回
    assert not can_transition(TrendStage.ARCHIVED, TrendStage.RISING)  # 终态
    with pytest.raises(IllegalStageTransition):
        assert_transition(TrendStage.ARCHIVED, TrendStage.RISING)


def test_same_stage_is_noop() -> None:
    assert_transition(TrendStage.RISING, TrendStage.RISING)  # 不抛


def test_archived_is_terminal() -> None:
    assert STAGE_TRANSITIONS[TrendStage.ARCHIVED] == frozenset()
