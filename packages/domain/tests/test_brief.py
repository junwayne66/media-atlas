"""ClaimTable 抽取 + Brief 组装 + 校验护栏：保真/去重/事实状态/默认配比/must_cover 违规。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    Claim,
    ClaimSourceStatus,
    CreationMode,
    CreativeOpportunity,
    EvidenceSpan,
    VideoBlueprint,
    VisualMix,
)
from videoforge_domain import (
    BriefIssueKind,
    build_claim_table,
    build_creative_brief,
    is_valid_brief,
    validate_brief,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _claim(cid, text, status=ClaimSourceStatus.UNVERIFIED) -> Claim:
    return Claim(
        id=cid, text=text, source_status=status,
        evidence=[EvidenceSpan(kind="transcript", ref_id="seg-0", start_ms=0, end_ms=1000)],
    )


def _blueprint(claims) -> VideoBlueprint:
    return VideoBlueprint(id="bp", duration_ms=45000, claims=claims, created_at=_T0)


def _opportunity() -> CreativeOpportunity:
    return CreativeOpportunity(
        id="opp-1", blueprint_id="bp", rationale="热点上升缺角度",
        target_platform="douyin", target_language="zh-CN", created_at=_T0,
    )


# —— ClaimTable 抽取 ——

def test_claim_table_carries_status_and_evidence() -> None:
    bp = _blueprint([_claim("c0", "事实一", ClaimSourceStatus.VERIFIED)])
    table = build_claim_table(bp, table_id="ct", created_at=_T0)
    assert table.source_blueprint_id == "bp"
    e = table.entries[0]
    assert e.claim_id == "c0" and e.fact_status is ClaimSourceStatus.VERIFIED
    assert e.evidence[0].ref_id == "seg-0"
    assert e.usable_in_rewrite is True


def test_claim_table_dedups_by_text() -> None:
    bp = _blueprint([_claim("c0", "同一句"), _claim("c1", "同一句"), _claim("c2", "另一句")])
    table = build_claim_table(bp, table_id="ct", created_at=_T0)
    assert len(table.entries) == 2  # 同文本去重


def test_disputed_claim_not_usable_in_rewrite() -> None:
    bp = _blueprint([_claim("c0", "有争议", ClaimSourceStatus.DISPUTED)])
    table = build_claim_table(bp, table_id="ct", created_at=_T0)
    assert table.entries[0].usable_in_rewrite is False


# —— Brief 组装 ——

def test_brief_defaults_visual_mix_by_mode() -> None:
    brief = build_creative_brief(
        _opportunity(), brief_id="b", created_at=_T0, objective="讲清影响",
        audience="AI 用户", angle="实测成本", duration_target_ms=45000,
        creation_mode=CreationMode.STRUCTURE_REWRITE,
    )
    assert brief.platform == "douyin"  # 取自 opportunity
    assert brief.opportunity_id == "opp-1" and brief.blueprint_id == "bp"
    assert brief.visual_mix is not None
    mix = brief.visual_mix
    assert abs((mix.talking_head + mix.screen_demo + mix.broll + mix.info_card) - 1.0) < 0.01


def test_brief_explicit_visual_mix_and_platform_override() -> None:
    brief = build_creative_brief(
        _opportunity(), brief_id="b", created_at=_T0, objective="x", audience="y",
        angle="z", duration_target_ms=30000, creation_mode=CreationMode.SOURCE_REEDIT,
        platform="tiktok",
        visual_mix=VisualMix(talking_head=0.1, screen_demo=0.5, broll=0.3, info_card=0.1),
    )
    assert brief.platform == "tiktok"
    assert brief.visual_mix.screen_demo == 0.5


# —— 校验护栏 ——

def test_valid_brief_passes() -> None:
    bp = _blueprint([_claim("c0", "事实一", ClaimSourceStatus.VERIFIED)])
    table = build_claim_table(bp, table_id="ct", created_at=_T0)
    brief = build_creative_brief(
        _opportunity(), brief_id="b", created_at=_T0, objective="x", audience="y", angle="z",
        duration_target_ms=45000, creation_mode=CreationMode.STRUCTURE_REWRITE,
        claim_table=table, must_cover_claim_ids=("c0",),
    )
    assert validate_brief(brief, table) == []
    assert is_valid_brief(brief, table)
    assert brief.claim_table_id == "ct"


def test_must_cover_missing_claim_detected() -> None:
    bp = _blueprint([_claim("c0", "事实一")])
    table = build_claim_table(bp, table_id="ct", created_at=_T0)
    brief = build_creative_brief(
        _opportunity(), brief_id="b", created_at=_T0, objective="x", audience="y", angle="z",
        duration_target_ms=45000, creation_mode=CreationMode.STRUCTURE_REWRITE,
        claim_table=table, must_cover_claim_ids=("ghost",),
    )
    kinds = {i.kind for i in validate_brief(brief, table)}
    assert BriefIssueKind.MUST_COVER_CLAIM_MISSING in kinds


def test_must_cover_disputed_claim_detected() -> None:
    bp = _blueprint([_claim("c0", "有争议", ClaimSourceStatus.DISPUTED)])
    table = build_claim_table(bp, table_id="ct", created_at=_T0)
    brief = build_creative_brief(
        _opportunity(), brief_id="b", created_at=_T0, objective="x", audience="y", angle="z",
        duration_target_ms=45000, creation_mode=CreationMode.STRUCTURE_REWRITE,
        claim_table=table, must_cover_claim_ids=("c0",),
    )
    kinds = {i.kind for i in validate_brief(brief, table)}
    # DISPUTED 事实既不可强制覆盖、又不可直接改写
    assert BriefIssueKind.MUST_COVER_CLAIM_DISPUTED in kinds
    assert BriefIssueKind.MUST_COVER_CLAIM_NOT_USABLE in kinds


def test_build_does_not_mutate_blueprint() -> None:
    bp = _blueprint([_claim("c0", "事实一")])
    before = bp.model_dump()
    build_claim_table(bp, table_id="ct", created_at=_T0)
    assert bp.model_dump() == before
