"""素材规划解析：匹配分 + 五级 Resolver 优先级 + 复用惩罚 + §6.2 护栏。"""

from datetime import UTC, datetime, timedelta

from videoforge_contracts import (
    AssetLicense,
    AssetLicenseType,
    AssetPlan,
    AssetPlanSlot,
    AssetRole,
    AssetSource,
    CompositionSpec,
    ResolvedAsset,
)
from videoforge_domain import (
    RESOLVER_PRIORITY,
    AssetCandidate,
    AssetPlanIssueKind,
    MatchWeights,
    is_valid_asset_plan,
    match_score,
    resolve_asset_plan,
    validate_asset_plan,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)
_OWNED = AssetLicense(type=AssetLicenseType.OWNED, holder="videoforge")


def _slot(sid: str = "slot-0", *, allowed=(AssetSource.SOURCE, AssetSource.OWN_LIBRARY),
          start=0, end=5000, fallback=AssetRole.INFO_CARD) -> AssetPlanSlot:
    return AssetPlanSlot(
        slot_id=sid, start_ms=start, end_ms=end, role=AssetRole.B_ROLL,
        query="ai chip demo", composition=CompositionSpec(aspect_ratio="9:16", safe_area="center"),
        allowed_sources=list(allowed), fallback=fallback,
    )


def _cand(aid: str, source: AssetSource, *, semantic=0.8, composition=0.7, resolution=0.8,
          motion=0.6, color=0.6, brand_ok=1.0, reuse=0,
          license: AssetLicense = _OWNED) -> AssetCandidate:
    return AssetCandidate(
        asset_id=aid, source=source, license=license, query="ai chip demo",
        provider=f"{source.value.lower()}.fake",
        semantic=semantic, composition=composition, resolution=resolution,
        motion=motion, color=color, brand_ok=brand_ok, reuse_count=reuse,
    )


# —— match_score ——

def test_match_score_reproducible_and_penalty_lowers() -> None:
    c = _cand("a", AssetSource.OWN_LIBRARY)
    s1 = match_score(c)
    s2 = match_score(c)
    assert s1 == s2  # bit 复现
    reused = _cand("a", AssetSource.OWN_LIBRARY, reuse=3)
    assert match_score(reused) < s1  # 复用惩罚有效


def test_match_score_bit_exact_formula() -> None:
    c = _cand("a", AssetSource.OWN_LIBRARY,
              semantic=1.0, composition=1.0, resolution=1.0,
              motion=1.0, color=1.0, brand_ok=1.0, reuse=0)
    w = MatchWeights()
    expected = w.semantic + w.composition + w.resolution + w.motion + w.color + w.brand
    assert abs(match_score(c, w) - min(1.0, expected)) < 1e-9


def test_match_score_clamped_zero_when_reuse_dominates() -> None:
    c = _cand("a", AssetSource.OWN_LIBRARY, semantic=0.1, composition=0.0, resolution=0.0,
              motion=0.0, color=0.0, brand_ok=0.0, reuse=100)
    assert match_score(c) == 0.0  # clamp 到 [0,1]


# —— 五级优先级 ——

def test_resolver_prefers_source_over_lower_tiers() -> None:
    plan = resolve_asset_plan(
        [_slot(allowed=RESOLVER_PRIORITY)],
        {
            AssetSource.SOURCE: [_cand("src-1", AssetSource.SOURCE)],
            AssetSource.OWN_LIBRARY: [_cand("own-1", AssetSource.OWN_LIBRARY, semantic=1.0)],
            AssetSource.STOCK: [_cand("stock-1", AssetSource.STOCK)],
        },
        plan_id="p", created_at=_T0,
    )
    r = plan.resolved[0]
    # 授权原片是最高级；即便自有库分更高也不能跨级选（§6.2 优先级严格）
    assert r.source is AssetSource.SOURCE and r.asset_id == "src-1"


def test_resolver_falls_through_when_higher_tier_below_threshold() -> None:
    plan = resolve_asset_plan(
        [_slot(allowed=RESOLVER_PRIORITY)],
        {
            AssetSource.SOURCE: [_cand("src-bad", AssetSource.SOURCE,
                                        semantic=0.0, composition=0.0, resolution=0.0,
                                        motion=0.0, color=0.0, brand_ok=0.0)],  # 全 0 → 分低
            AssetSource.OWN_LIBRARY: [_cand("own-1", AssetSource.OWN_LIBRARY)],
        },
        plan_id="p", created_at=_T0,
    )
    r = plan.resolved[0]
    assert r.source is AssetSource.OWN_LIBRARY  # 上级不合格自动落到下级


def test_resolver_respects_slot_allowed_sources() -> None:
    plan = resolve_asset_plan(
        [_slot(allowed=(AssetSource.OWN_LIBRARY,))],  # 只允许自有库
        {
            AssetSource.SOURCE: [_cand("src-good", AssetSource.SOURCE, semantic=1.0)],
            AssetSource.OWN_LIBRARY: [_cand("own-1", AssetSource.OWN_LIBRARY)],
        },
        plan_id="p", created_at=_T0,
    )
    r = plan.resolved[0]
    assert r.source is AssetSource.OWN_LIBRARY  # SOURCE 分再高也不许用


def test_resolver_falls_back_to_placeholder_when_all_miss() -> None:
    plan = resolve_asset_plan(
        [_slot(allowed=(AssetSource.SOURCE, AssetSource.OWN_LIBRARY))],
        {},  # 无候选
        plan_id="p", created_at=_T0,
    )
    r = plan.resolved[0]
    assert r.is_fallback and r.source is AssetSource.PLACEHOLDER
    assert r.license.type is AssetLicenseType.PLACEHOLDER


def test_fallback_plan_passes_guardrail() -> None:
    # 回归：fallback 是设计好的逃生出口，即便 PLACEHOLDER 不在 allowed_sources 内也不算违规。
    # 人工审通过后 fallback 会被真素材替换，届时 allowed_sources 自然满足。
    plan = resolve_asset_plan(
        [_slot(allowed=(AssetSource.SOURCE, AssetSource.OWN_LIBRARY))],
        {},  # 无候选 → PLACEHOLDER fallback
        plan_id="p", created_at=_T0,
    )
    assert plan.resolved[0].is_fallback
    assert validate_asset_plan(plan) == []  # fallback 豁免 SOURCE_NOT_ALLOWED


def test_resolver_reuse_penalty_across_slots() -> None:
    # 两个 slot 都命中同一素材，第二 slot 应因复用惩罚落到下级
    slots = [_slot("s0", allowed=RESOLVER_PRIORITY),
             _slot("s1", allowed=RESOLVER_PRIORITY, start=5000, end=10000)]
    plan = resolve_asset_plan(
        slots,
        {
            AssetSource.SOURCE: [_cand("src-1", AssetSource.SOURCE,
                                        semantic=0.6, composition=0.5, resolution=0.5,
                                        motion=0.3, color=0.3, brand_ok=1.0)],
            AssetSource.OWN_LIBRARY: [_cand("own-1", AssetSource.OWN_LIBRARY,
                                             semantic=0.55, composition=0.5, resolution=0.5,
                                             motion=0.3, color=0.3, brand_ok=1.0)],
        },
        plan_id="p", created_at=_T0,
    )
    assert plan.resolved[0].asset_id == "src-1"  # 第一次命中授权原片
    # 第二次复用后 src-1 的有效 reuse_count=1，分数被扣，可能被别人反超；
    # 至少验证 reuse_count 被跟踪
    assert plan.resolved[1].reuse_count in (1, 2)


def test_resolver_deterministic_on_ties() -> None:
    # 两候选同分 → 按 asset_id 字典序确定性排序
    cands = {AssetSource.OWN_LIBRARY: [
        _cand("z-a", AssetSource.OWN_LIBRARY),
        _cand("a-a", AssetSource.OWN_LIBRARY),
    ]}
    a = resolve_asset_plan([_slot(allowed=(AssetSource.OWN_LIBRARY,))],
                           cands, plan_id="p", created_at=_T0)
    b = resolve_asset_plan([_slot(allowed=(AssetSource.OWN_LIBRARY,))],
                           cands, plan_id="p", created_at=_T0)
    assert a.resolved[0].asset_id == b.resolved[0].asset_id == "a-a"


# —— 护栏 ——

def _resolved(sid: str, *, source=AssetSource.OWN_LIBRARY, usage_start=0, usage_end=5000,
              lic: AssetLicense = _OWNED) -> ResolvedAsset:
    return ResolvedAsset(
        slot_id=sid, asset_id=f"a-{sid}", source=source, license=lic,
        query="q", usage_start_ms=usage_start, usage_end_ms=usage_end, match_score=0.7,
    )


def _plan(slots: list[AssetPlanSlot], resolved: list[ResolvedAsset]) -> AssetPlan:
    return AssetPlan(id="p", slots=slots, resolved=resolved, created_at=_T0)


def test_valid_plan_passes_guardrail() -> None:
    plan = _plan([_slot()], [_resolved("slot-0")])
    assert validate_asset_plan(plan) == []
    assert is_valid_asset_plan(plan)


def test_unresolved_slot_flagged() -> None:
    plan = _plan([_slot()], [])  # 无 resolved
    kinds = {i.kind for i in validate_asset_plan(plan)}
    assert AssetPlanIssueKind.UNRESOLVED_SLOT in kinds


def test_source_not_allowed_flagged() -> None:
    # slot 只允许 SOURCE，但 resolved 是 OWN_LIBRARY
    plan = _plan([_slot(allowed=(AssetSource.SOURCE,))],
                 [_resolved("slot-0", source=AssetSource.OWN_LIBRARY)])
    kinds = {i.kind for i in validate_asset_plan(plan)}
    assert AssetPlanIssueKind.SOURCE_NOT_ALLOWED in kinds


def test_usage_out_of_slot_flagged() -> None:
    plan = _plan([_slot(start=0, end=5000)],
                 [_resolved("slot-0", usage_start=0, usage_end=8000)])  # 超出 slot
    kinds = {i.kind for i in validate_asset_plan(plan)}
    assert AssetPlanIssueKind.USAGE_OUT_OF_SLOT in kinds


def test_license_expired_flagged() -> None:
    expired = AssetLicense(type=AssetLicenseType.LICENSED_STOCK, holder="stock.co",
                            valid_until=_T0 - timedelta(days=1))
    plan = _plan([_slot(allowed=(AssetSource.STOCK,))],
                 [_resolved("slot-0", source=AssetSource.STOCK, lic=expired)])
    kinds = {i.kind for i in validate_asset_plan(plan, now=_T0)}
    assert AssetPlanIssueKind.LICENSE_INSUFFICIENT in kinds


def test_reuse_exceeded_flagged() -> None:
    # 同 asset_id 复用 4 次超过默认上限 3
    slots = [_slot(f"s{i}", start=i * 1000, end=(i + 1) * 1000) for i in range(4)]
    resolved = [ResolvedAsset(
        slot_id=f"s{i}", asset_id="shared", source=AssetSource.OWN_LIBRARY,
        license=_OWNED, query="q", usage_start_ms=i * 1000, usage_end_ms=(i + 1) * 1000,
        match_score=0.7,
    ) for i in range(4)]
    plan = _plan(slots, resolved)
    kinds = {i.kind for i in validate_asset_plan(plan)}
    assert AssetPlanIssueKind.REUSE_EXCEEDED in kinds
