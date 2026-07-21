"""能力路由：过滤 + 加权评分，结果必须可解释（docs/00 §6 原则 8）。

评分公式与权重照抄 docs/architecture/30 §6：
    score = cache_hit*0.30 + locality*0.25 + estimated_latency*0.20
          + estimated_cost*0.15 + reliability*0.10
"""

from dataclasses import dataclass

from videoforge_contracts import ExecutionPolicy
from videoforge_provider_sdk.registry import ProviderRegistry, ProviderRuntime

WEIGHTS = {
    "cache_hit": 0.30,
    "locality": 0.25,
    "estimated_latency": 0.20,
    "estimated_cost": 0.15,
    "reliability": 0.10,
}


class NoEligibleProviderError(Exception):
    def __init__(self, capability: str, rejected: list[tuple[str, str]]) -> None:
        detail = "; ".join(f"{name}: {reason}" for name, reason in rejected) or "无已注册 provider"
        super().__init__(f"能力 {capability} 无可用 provider（{detail}）")
        self.capability = capability
        self.rejected = rejected


@dataclass(frozen=True)
class CandidateScore:
    name: str
    score: float
    breakdown: dict[str, float]


@dataclass(frozen=True)
class RouteDecision:
    capability: str
    selected: str
    score: float
    breakdown: dict[str, float]
    candidates: list[CandidateScore]
    rejected: list[tuple[str, str]]  # (name, reason code)


def _filter_reason(
    entry: ProviderRuntime,
    capability: str,
    language: str | None,
    platform: str | None,
    policy: ExecutionPolicy,
) -> str | None:
    d = entry.provider.descriptor
    if entry.disabled:
        return "disabled"
    if capability not in d.capabilities:
        return "capability_missing"
    if language is not None and d.languages and language not in d.languages:
        return "language_unsupported"
    if platform is not None and d.platforms and platform not in d.platforms:
        return "platform_unsupported"
    if policy == ExecutionPolicy.LOCAL_ONLY and d.execution_location == "cloud":
        return "policy_local_only"
    if policy == ExecutionPolicy.CLOUD_ONLY and d.execution_location == "local":
        return "policy_cloud_only"
    if not entry.breaker.allow_request():
        return "circuit_open"
    return None


def _locality_score(location: str, policy: ExecutionPolicy) -> float:
    preference = {
        ExecutionPolicy.LOCAL_PREFERRED: "local",
        ExecutionPolicy.CLOUD_PREFERRED: "cloud",
    }.get(policy)
    if preference is None:  # *_ONLY 已在过滤阶段裁掉不合规者，剩者等价
        return 1.0
    if location == preference:
        return 1.0
    if location == "hybrid":
        return 0.5
    return 0.0


def _score(
    entry: ProviderRuntime, policy: ExecutionPolicy, cache_hints: dict[str, float]
) -> CandidateScore:
    d = entry.provider.descriptor
    cost = d.cost_model.estimated_cost_per_unit if d.cost_model else None
    breakdown = {
        "cache_hit": min(1.0, max(0.0, cache_hints.get(d.name, 0.0))),
        "locality": _locality_score(d.execution_location, policy),
        "estimated_latency": (
            0.5 if entry.latency_ema_s is None else 1.0 / (1.0 + entry.latency_ema_s)
        ),
        "estimated_cost": 0.5 if cost is None else 1.0 / (1.0 + cost),
        "reliability": entry.reliability,
    }
    total = sum(WEIGHTS[k] * v for k, v in breakdown.items())
    return CandidateScore(name=d.name, score=round(total, 6), breakdown=breakdown)


def route(
    registry: ProviderRegistry,
    capability: str,
    *,
    language: str | None = None,
    platform: str | None = None,
    policy: ExecutionPolicy = ExecutionPolicy.LOCAL_PREFERRED,
    cache_hints: dict[str, float] | None = None,
) -> RouteDecision:
    cache_hints = cache_hints or {}
    rejected: list[tuple[str, str]] = []
    scored: list[CandidateScore] = []
    for entry in registry.all():
        reason = _filter_reason(entry, capability, language, platform, policy)
        if reason is not None:
            rejected.append((entry.provider.descriptor.name, reason))
            continue
        scored.append(_score(entry, policy, cache_hints))

    if not scored:
        raise NoEligibleProviderError(capability, rejected)

    scored.sort(key=lambda c: (-c.score, c.name))  # 分数优先，同分按名字稳定
    best = scored[0]
    registry.get(best.name).breaker.reserve_probe()  # 半开者被选中即占用唯一探针名额
    return RouteDecision(
        capability=capability,
        selected=best.name,
        score=best.score,
        breakdown=best.breakdown,
        candidates=scored,
        rejected=rejected,
    )
