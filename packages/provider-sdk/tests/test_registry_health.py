"""DoD：健康降级测试——熔断打开即从路由中剔除，冷却后半开试探恢复。"""

import pytest
from provider_factories import make_provider

from videoforge_provider_sdk import (
    CircuitState,
    NoEligibleProviderError,
    ProviderInvokeError,
    ProviderRegistry,
    route,
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def test_circuit_open_degrades_to_fallback_provider() -> None:
    clock = FakeClock()
    registry = ProviderRegistry(failure_threshold=3, cooldown_s=60, now_fn=clock)
    registry.register(make_provider(name="asr.primary", cost_model=None))
    registry.register(make_provider(name="asr.backup", execution_location="cloud"))

    assert route(registry, "asr.transcribe").selected == "asr.primary"

    for _ in range(3):
        registry.record_result("asr.primary", success=False)
    assert registry.get("asr.primary").breaker.state == CircuitState.OPEN

    degraded = route(registry, "asr.transcribe")
    assert degraded.selected == "asr.backup"
    assert ("asr.primary", "circuit_open") in degraded.rejected


def test_cooldown_half_open_recovers_primary() -> None:
    clock = FakeClock()
    registry = ProviderRegistry(failure_threshold=1, cooldown_s=60, now_fn=clock)
    registry.register(make_provider(name="asr.primary"))
    registry.register(make_provider(name="asr.backup", execution_location="cloud"))

    registry.record_result("asr.primary", success=False)
    assert route(registry, "asr.transcribe").selected == "asr.backup"

    clock.advance(60)  # 冷却结束 → 半开，重新参与路由
    trial = route(registry, "asr.transcribe")
    assert trial.selected == "asr.primary"

    # 探针结果未出前，半开者不再被选中——流量继续走备选，不放大故障
    second = route(registry, "asr.transcribe")
    assert second.selected == "asr.backup"
    assert ("asr.primary", "circuit_open") in second.rejected

    registry.record_result("asr.primary", success=True)
    assert registry.get("asr.primary").breaker.state == CircuitState.CLOSED
    assert registry.get("asr.primary").last_success_at == 60.0


def test_all_circuits_open_raises_with_reasons() -> None:
    registry = ProviderRegistry(failure_threshold=1)
    registry.register(make_provider(name="only.one"))
    registry.record_result("only.one", success=False)
    with pytest.raises(NoEligibleProviderError) as exc:
        route(registry, "asr.transcribe")
    assert exc.value.rejected == [("only.one", "circuit_open")]


def test_disable_is_kill_switch() -> None:
    registry = ProviderRegistry()
    registry.register(make_provider(name="p.a"))
    registry.disable("p.a")
    with pytest.raises(NoEligibleProviderError) as exc:
        route(registry, "asr.transcribe")
    assert exc.value.rejected == [("p.a", "disabled")]
    registry.enable("p.a")
    assert route(registry, "asr.transcribe").selected == "p.a"


async def test_fake_provider_invoke_and_failure_scripting() -> None:
    provider = make_provider(name="f.p")
    provider.fail_times(1)
    with pytest.raises(ProviderInvokeError):
        await provider.invoke("asr.transcribe", {"a": 1})
    result = await provider.invoke("asr.transcribe", {"a": 1})
    assert result["provider"] == "f.p"
    assert result["echo"] == {"a": 1}
    with pytest.raises(ProviderInvokeError, match="不支持能力"):
        await provider.invoke("tts.speak", {})


def test_duplicate_registration_rejected() -> None:
    registry = ProviderRegistry()
    registry.register(make_provider(name="p.a"))
    with pytest.raises(ValueError, match="已注册"):
        registry.register(make_provider(name="p.a"))
