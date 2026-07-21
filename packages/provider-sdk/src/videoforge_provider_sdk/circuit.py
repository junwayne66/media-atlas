"""熔断器：closed → open →（冷却后）half_open → closed/open。

时钟可注入，测试用假时钟推进冷却期，不依赖真实时间。
"""

import time
from collections.abc import Callable
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_s: float = 60.0,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold 至少为 1")
        self._threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._now = now_fn
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_probe_inflight = False

    @property
    def state(self) -> CircuitState:
        self._maybe_transition_half_open()
        return self._state

    def _maybe_transition_half_open(self) -> None:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if self._now() - self._opened_at >= self._cooldown_s:
                self._state = CircuitState.HALF_OPEN
                self._half_open_probe_inflight = False

    def allow_request(self) -> bool:
        """纯窥探，无副作用；实际占用半开探针名额用 reserve_probe()。"""
        state = self.state
        if state == CircuitState.OPEN:
            return False
        if state == CircuitState.HALF_OPEN and self._half_open_probe_inflight:
            return False
        return True

    def reserve_probe(self) -> None:
        """半开只放一个探针：被路由选中即占位，record_* 出结果前不再放行。"""
        if self.state == CircuitState.HALF_OPEN:
            self._half_open_probe_inflight = True

    def record_success(self) -> None:
        # OPEN 期间在途请求成功返回也视为恢复证据，直接闭合（有意为之）
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None
        self._half_open_probe_inflight = False

    def record_failure(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self._trip()  # 半开试探失败：立刻重新打开并重置冷却
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._now()
        self._consecutive_failures = 0
        self._half_open_probe_inflight = False
