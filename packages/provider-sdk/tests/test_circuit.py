from videoforge_provider_sdk import CircuitBreaker, CircuitState


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def make(threshold: int = 3, cooldown: float = 60.0) -> tuple[CircuitBreaker, FakeClock]:
    clock = FakeClock()
    return CircuitBreaker(failure_threshold=threshold, cooldown_s=cooldown, now_fn=clock), clock


def test_opens_after_threshold_consecutive_failures() -> None:
    breaker, _ = make(threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False


def test_success_resets_failure_streak() -> None:
    breaker, _ = make(threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED  # 未连续到阈值


def test_cooldown_transitions_to_half_open_then_success_closes() -> None:
    breaker, clock = make(threshold=1, cooldown=60)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    clock.advance(59)
    assert breaker.allow_request() is False
    clock.advance(1)
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.allow_request() is True
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


def test_half_open_single_probe_reservation() -> None:
    breaker, clock = make(threshold=1, cooldown=60)
    breaker.record_failure()
    clock.advance(60)
    assert breaker.allow_request() is True
    assert breaker.allow_request() is True  # 窥探无副作用
    breaker.reserve_probe()  # 被选中：占用唯一探针
    assert breaker.allow_request() is False
    breaker.record_success()
    assert breaker.allow_request() is True  # 闭合后恢复正常放行


def test_half_open_failure_reopens_with_fresh_cooldown() -> None:
    breaker, clock = make(threshold=1, cooldown=60)
    breaker.record_failure()
    clock.advance(60)
    assert breaker.state == CircuitState.HALF_OPEN
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    clock.advance(59)
    assert breaker.allow_request() is False
    clock.advance(1)
    assert breaker.state == CircuitState.HALF_OPEN
