"""Provider 注册表：运行时健康状态、熔断、一键禁用与调用统计。

连接器必备能力清单见 docs/architecture/30 §9：限流器、错误映射、回退路径、
最后成功时间、一键禁用——本层承担健康/禁用/统计；限流与错误映射在各
Connector 实现内（VF-1xx 起）。
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from videoforge_provider_sdk.base import Provider
from videoforge_provider_sdk.circuit import CircuitBreaker


@dataclass
class ProviderRuntime:
    provider: Provider
    breaker: CircuitBreaker
    disabled: bool = False
    total_calls: int = 0
    total_successes: int = 0
    last_success_at: float | None = None
    latency_ema_s: float | None = field(default=None)

    @property
    def reliability(self) -> float:
        if self.total_calls == 0:
            return 1.0  # 无数据视为可靠，冷启动不被压制
        return self.total_successes / self.total_calls


class ProviderRegistry:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_s: float = 60.0,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._now = now_fn
        self._failure_threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._entries: dict[str, ProviderRuntime] = {}

    def register(self, provider: Provider) -> None:
        name = provider.descriptor.name
        if name in self._entries:
            raise ValueError(f"provider 已注册: {name}")
        self._entries[name] = ProviderRuntime(
            provider=provider,
            breaker=CircuitBreaker(
                failure_threshold=self._failure_threshold,
                cooldown_s=self._cooldown_s,
                now_fn=self._now,
            ),
        )

    def get(self, name: str) -> ProviderRuntime:
        return self._entries[name]

    def all(self) -> list[ProviderRuntime]:
        return list(self._entries.values())

    def disable(self, name: str) -> None:
        self._entries[name].disabled = True

    def enable(self, name: str) -> None:
        self._entries[name].disabled = False

    def record_result(self, name: str, *, success: bool, duration_s: float | None = None) -> None:
        entry = self._entries[name]
        entry.total_calls += 1
        if success:
            entry.total_successes += 1
            entry.last_success_at = self._now()
            entry.breaker.record_success()
        else:
            entry.breaker.record_failure()
        # 只用成功调用更新时延 EMA：失败（如超时 9s）不应污染时延估计
        if success and duration_s is not None:
            if entry.latency_ema_s is None:
                entry.latency_ema_s = duration_s
            else:
                entry.latency_ema_s = 0.7 * entry.latency_ema_s + 0.3 * duration_s
