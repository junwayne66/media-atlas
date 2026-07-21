"""DoD：能力/语言/位置/成本路由测试（docs/architecture/30 §6 权重公式）。"""

import pytest
from provider_factories import cost, make_provider

from videoforge_contracts import ExecutionPolicy
from videoforge_provider_sdk import (
    WEIGHTS,
    NoEligibleProviderError,
    ProviderRegistry,
    route,
)


def test_weights_match_architecture_doc() -> None:
    assert WEIGHTS == {
        "cache_hit": 0.30,
        "locality": 0.25,
        "estimated_latency": 0.20,
        "estimated_cost": 0.15,
        "reliability": 0.10,
    }
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_capability_filter_with_reason_codes() -> None:
    registry = ProviderRegistry()
    registry.register(make_provider(name="asr.a", capabilities=["asr.transcribe"]))
    registry.register(make_provider(name="ocr.b", capabilities=["ocr.detect"]))

    decision = route(registry, "asr.transcribe")
    assert decision.selected == "asr.a"
    assert ("ocr.b", "capability_missing") in decision.rejected

    with pytest.raises(NoEligibleProviderError) as exc:
        route(registry, "tts.speak")
    assert {r for _, r in exc.value.rejected} == {"capability_missing"}


def test_language_and_platform_filters() -> None:
    registry = ProviderRegistry()
    registry.register(make_provider(name="asr.zh", languages=["zh-CN"]))
    registry.register(make_provider(name="asr.en", languages=["en-US"]))
    registry.register(make_provider(name="asr.any"))  # 空 languages = 通用

    decision = route(registry, "asr.transcribe", language="zh-CN")
    assert {c.name for c in decision.candidates} == {"asr.zh", "asr.any"}
    assert ("asr.en", "language_unsupported") in decision.rejected

    registry2 = ProviderRegistry()
    registry2.register(make_provider(name="src.dy", platforms=["douyin"]))
    registry2.register(make_provider(name="src.tt", platforms=["tiktok"]))
    decision2 = route(registry2, "asr.transcribe", platform="tiktok")
    assert decision2.selected == "src.tt"
    assert ("src.dy", "platform_unsupported") in decision2.rejected


def test_execution_policy_filters_and_locality_preference() -> None:
    registry = ProviderRegistry()
    registry.register(make_provider(name="p.local", execution_location="local"))
    registry.register(make_provider(name="p.cloud", execution_location="cloud"))

    only_local = route(registry, "asr.transcribe", policy=ExecutionPolicy.LOCAL_ONLY)
    assert only_local.selected == "p.local"
    assert ("p.cloud", "policy_local_only") in only_local.rejected

    only_cloud = route(registry, "asr.transcribe", policy=ExecutionPolicy.CLOUD_ONLY)
    assert only_cloud.selected == "p.cloud"
    assert ("p.local", "policy_cloud_only") in only_cloud.rejected

    prefer_local = route(registry, "asr.transcribe", policy=ExecutionPolicy.LOCAL_PREFERRED)
    assert prefer_local.selected == "p.local"
    prefer_cloud = route(registry, "asr.transcribe", policy=ExecutionPolicy.CLOUD_PREFERRED)
    assert prefer_cloud.selected == "p.cloud"


def test_cheaper_provider_wins_when_otherwise_equal() -> None:
    registry = ProviderRegistry()
    registry.register(make_provider(name="tts.cheap", cost_model=cost(0.1)))
    registry.register(make_provider(name="tts.pricey", cost_model=cost(5.0)))

    decision = route(registry, "asr.transcribe")
    assert decision.selected == "tts.cheap"
    cheap = next(c for c in decision.candidates if c.name == "tts.cheap")
    pricey = next(c for c in decision.candidates if c.name == "tts.pricey")
    assert cheap.breakdown["estimated_cost"] > pricey.breakdown["estimated_cost"]


def test_reliability_from_recorded_results_affects_ranking() -> None:
    registry = ProviderRegistry()
    registry.register(make_provider(name="a.stable"))
    registry.register(make_provider(name="a.flaky"))
    for _ in range(4):
        registry.record_result("a.stable", success=True)
    registry.record_result("a.flaky", success=True)
    registry.record_result("a.flaky", success=False)  # 可靠性 0.5，未触发熔断

    decision = route(registry, "asr.transcribe")
    assert decision.selected == "a.stable"
    assert decision.breakdown["reliability"] == 1.0


def test_cache_hint_dominates_per_weight_table() -> None:
    registry = ProviderRegistry()
    registry.register(make_provider(name="r.hot"))
    registry.register(make_provider(name="r.cold"))
    decision = route(registry, "asr.transcribe", cache_hints={"r.hot": 1.0})
    assert decision.selected == "r.hot"
    assert decision.score - min(c.score for c in decision.candidates) == pytest.approx(0.30)


def test_decision_is_explainable() -> None:
    registry = ProviderRegistry()
    registry.register(make_provider(name="only.one"))
    decision = route(registry, "asr.transcribe")
    assert set(decision.breakdown) == set(WEIGHTS)
    assert decision.score == pytest.approx(
        sum(WEIGHTS[k] * v for k, v in decision.breakdown.items())
    )
