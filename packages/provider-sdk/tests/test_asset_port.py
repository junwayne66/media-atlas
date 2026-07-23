"""素材源端口：Unconfigured 诚实 + Fake 确定性/不泄漏许可 + 端到端过纯域五级解析与护栏。

端到端（provider-sdk 测试可依赖 domain 做验收，同 highlight/reedit 先例）：
多源 Fake candidates → domain.AssetCandidate 映射 → resolve_asset_plan → validate_asset_plan == []。
"""

from datetime import UTC, datetime

from videoforge_contracts import (
    AssetLicense,
    AssetLicenseType,
    AssetPlanSlot,
    AssetRole,
    AssetSource,
    CompositionSpec,
)
from videoforge_domain import AssetCandidate, resolve_asset_plan, validate_asset_plan
from videoforge_provider_sdk import (
    AssetCandidateSpec,
    AssetSearchRequest,
    AssetSourceProvider,
    AssetSourceStatus,
    FakeAssetSourceProvider,
    UnconfiguredAssetSourceProvider,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)
_OWNED = AssetLicense(type=AssetLicenseType.OWNED, holder="videoforge")
_STOCK = AssetLicense(type=AssetLicenseType.LICENSED_STOCK, holder="stock.co")


def _spec(aid: str, source: AssetSource, *, semantic=0.8, license=_OWNED) -> AssetCandidateSpec:
    return AssetCandidateSpec(
        asset_id=aid, source=source, license=license, query="q",
        provider=f"{source.value.lower()}.fake",
        semantic=semantic, composition=0.7, resolution=0.7, motion=0.5, color=0.5, brand_ok=1.0,
    )


def _slot() -> AssetPlanSlot:
    return AssetPlanSlot(
        slot_id="slot-0", start_ms=0, end_ms=5000, role=AssetRole.B_ROLL, query="ai chip demo",
        composition=CompositionSpec(aspect_ratio="9:16", safe_area="center"),
        allowed_sources=[AssetSource.SOURCE, AssetSource.OWN_LIBRARY, AssetSource.STOCK],
        fallback=AssetRole.INFO_CARD,
    )


def _to_domain_cand(s: AssetCandidateSpec) -> AssetCandidate:
    return AssetCandidate(
        asset_id=s.asset_id, source=s.source, license=s.license, query=s.query,
        provider=s.provider, semantic=s.semantic, composition=s.composition,
        resolution=s.resolution, motion=s.motion, color=s.color, brand_ok=s.brand_ok,
        reuse_count=s.reuse_count,
    )


def test_protocol_conformance() -> None:
    for src in (AssetSource.SOURCE, AssetSource.OWN_LIBRARY, AssetSource.STOCK):
        assert isinstance(FakeAssetSourceProvider(src), AssetSourceProvider)
        assert isinstance(UnconfiguredAssetSourceProvider(src), AssetSourceProvider)


def test_unconfigured_is_honest() -> None:
    prov = UnconfiguredAssetSourceProvider(AssetSource.STOCK)
    result = prov.search(AssetSearchRequest(query="q", role="B_ROLL", aspect_ratio="9:16"))
    assert result.status is AssetSourceStatus.UNCONFIGURED
    assert result.candidates == []  # 绝不静默造候选
    assert result.error_code is not None
    assert prov.health_check().status is AssetSourceStatus.UNCONFIGURED


def test_fake_deterministic_and_deep_copies_license() -> None:
    pool = {"B_ROLL": [_spec("a", AssetSource.OWN_LIBRARY)]}
    fake = FakeAssetSourceProvider(AssetSource.OWN_LIBRARY, pool=pool)
    req = AssetSearchRequest(query="q", role="B_ROLL", aspect_ratio="9:16")
    r1 = fake.search(req)
    r2 = fake.search(req)
    assert r1.ok and len(r1.candidates) == 1
    assert r1.candidates[0].license.holder == r2.candidates[0].license.holder  # 复现
    # 深拷贝：调用方回写返回的 license 不影响后续 search
    r1.candidates[0].license.notes = "tampered"
    r3 = fake.search(req)
    assert r3.candidates[0].license.notes is None  # 未被污染


def test_end_to_end_multi_source_resolve() -> None:
    # SOURCE 与 OWN_LIBRARY 都有候选，Resolver 应按优先级选中 SOURCE
    src_fake = FakeAssetSourceProvider(AssetSource.SOURCE, pool={
        "B_ROLL": [_spec("src-1", AssetSource.SOURCE, semantic=0.6)],
    })
    own_fake = FakeAssetSourceProvider(AssetSource.OWN_LIBRARY, pool={
        "B_ROLL": [_spec("own-1", AssetSource.OWN_LIBRARY, semantic=0.9)],
    })
    stock_fake = FakeAssetSourceProvider(AssetSource.STOCK, pool={
        "B_ROLL": [_spec("stock-1", AssetSource.STOCK, license=_STOCK)],
    })
    req = AssetSearchRequest(query="ai chip demo", role="B_ROLL", aspect_ratio="9:16")
    candidates_by_source = {
        AssetSource.SOURCE: [_to_domain_cand(c) for c in src_fake.search(req).candidates],
        AssetSource.OWN_LIBRARY: [_to_domain_cand(c) for c in own_fake.search(req).candidates],
        AssetSource.STOCK: [_to_domain_cand(c) for c in stock_fake.search(req).candidates],
    }

    plan = resolve_asset_plan([_slot()], candidates_by_source, plan_id="p", created_at=_T0)
    assert plan.resolved[0].source is AssetSource.SOURCE
    assert plan.resolved[0].asset_id == "src-1"
    # 每 ResolvedAsset 必带来源+许可+检索词+使用区间（§6.2 可溯性）
    r = plan.resolved[0]
    assert r.source and r.license and r.query and r.usage_start_ms == 0 and r.usage_end_ms == 5000
    # 核心验收：Fake 驱动的多源解析结果直接过纯域护栏
    assert validate_asset_plan(plan, now=_T0) == []


def test_fake_deep_copies_input_licenses() -> None:
    # 回归：调用方回写自己持有的 license 对象不得污染 Fake 内部池的后续 search 结果。
    lic = AssetLicense(type=AssetLicenseType.OWNED, holder="orig-holder", notes="orig")
    spec = _spec("a1", AssetSource.OWN_LIBRARY, license=lic)
    fake = FakeAssetSourceProvider(AssetSource.OWN_LIBRARY, pool={"B_ROLL": [spec]})
    # 构造后调用方回写自己持有的 license
    lic.notes = "TAMPERED-INPUT"
    lic.holder = "TAMPERED-HOLDER"
    result = fake.search(AssetSearchRequest(query="q", role="B_ROLL", aspect_ratio="9:16"))
    assert result.candidates[0].license.notes == "orig"  # 内部池未被外部污染
    assert result.candidates[0].license.holder == "orig-holder"


def test_fake_never_fabricates_license() -> None:
    # Fake 只回放构造时注入的候选；无对应 role 时返回空列表，绝不凭空造 license
    fake = FakeAssetSourceProvider(AssetSource.STOCK, pool={"TALKING_HEAD": [
        _spec("t-1", AssetSource.STOCK, license=_STOCK),
    ]})
    result = fake.search(AssetSearchRequest(query="q", role="B_ROLL", aspect_ratio="9:16"))
    assert result.ok and result.candidates == []
