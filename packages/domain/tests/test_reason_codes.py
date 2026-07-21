"""reason code 推导（docs/modules/40 §7/§10：Top-20 需 ≥2 条）。"""

from videoforge_contracts import TrendStage, TrendSubScores
from videoforge_domain import derive_reason_codes


def _subs(**over) -> TrendSubScores:
    base = dict(velocity=0.0, acceleration=0.0, engagement_efficiency=0.0)
    base.update(over)
    return TrendSubScores(**base)


def test_hot_cluster_gets_at_least_two_codes() -> None:
    codes = derive_reason_codes(
        _subs(velocity=0.7, acceleration=0.6, cross_platform_score=0.8, topic_fit=0.9),
        TrendStage.RISING,
    )
    assert len(codes) >= 2
    assert "HIGH_ACCELERATION" in codes
    assert "CROSS_PLATFORM" in codes


def test_codes_are_stable_ordered() -> None:
    codes = derive_reason_codes(
        _subs(velocity=0.9, acceleration=0.9, cross_platform_score=0.9), TrendStage.RISING
    )
    # 顺序按规则声明：acceleration 在 velocity 之前，velocity 在 cross_platform 之前
    assert codes.index("HIGH_ACCELERATION") < codes.index("HIGH_VELOCITY")
    assert codes.index("HIGH_VELOCITY") < codes.index("CROSS_PLATFORM")


def test_stage_specific_code_appended() -> None:
    assert "EARLY_STAGE" in derive_reason_codes(_subs(acceleration=0.8), TrendStage.EMERGING)
    assert "PAST_PEAK" in derive_reason_codes(_subs(decay=0.7), TrendStage.DECAYING)
    assert "SUPPLY_SATURATED" in derive_reason_codes(_subs(saturation=0.8), TrendStage.SATURATED)


def test_saturation_and_decay_flagged() -> None:
    codes = derive_reason_codes(_subs(saturation=0.7, decay=0.6), TrendStage.DECAYING)
    assert "HIGH_SATURATION" in codes
    assert "DECAYING_SIGNAL" in codes


def test_cold_cluster_has_no_positive_codes() -> None:
    codes = derive_reason_codes(_subs(velocity=0.1, acceleration=0.1), TrendStage.EMERGING)
    assert codes == ["EARLY_STAGE"]
