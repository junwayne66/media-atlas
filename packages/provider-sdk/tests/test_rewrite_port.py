"""结构重写端口：Unconfigured 诚实 + Fake 端到端过 domain 护栏 + 拒引争议事实。

端到端链路（provider-sdk 测试可依赖 domain 做验收，同 blueprint_fusion/vlm/ocr 先例）：
VideoBlueprint → build_claim_table + build_beat_template → CreativeBrief →
FakeStructureRewriteProvider.rewrite → domain.validate_script == []（不抄源/引真实事实/合预算）。
"""

from datetime import UTC, datetime

from videoforge_contracts import (
    Claim,
    ClaimSourceStatus,
    CreationMode,
    CreativeOpportunity,
    EvidenceSpan,
    RhetoricalBeat,
    RhetoricalBeatKind,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
    VideoBlueprint,
)
from videoforge_domain import (
    build_beat_template,
    build_claim_table,
    build_creative_brief,
    validate_script,
)
from videoforge_provider_sdk import (
    FakeStructureRewriteProvider,
    RewriteErrorCode,
    RewriteRequest,
    RewriteStatus,
    StructureRewriteProvider,
    UnconfiguredStructureRewriteProvider,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _evidence() -> EvidenceSpan:
    return EvidenceSpan(kind="transcript", ref_id="seg-0", start_ms=0, end_ms=2000)


def _blueprint(*, claims, lang="zh-CN") -> VideoBlueprint:
    beats = [
        RhetoricalBeat(
            id="r0", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=3000, summary="钩子"
        ),
        RhetoricalBeat(
            id="r1", kind=RhetoricalBeatKind.EVIDENCE, start_ms=3000, end_ms=12000, summary="证据"
        ),
        RhetoricalBeat(
            id="r2", kind=RhetoricalBeatKind.CTA, start_ms=12000, end_ms=15000, summary="引导"
        ),
    ]
    return VideoBlueprint(
        id="bp",
        source_artifact_id="art-0",
        duration_ms=15000,
        claims=claims,
        rhetorical_beats=beats,
        created_at=_T0,
    )


def _opportunity() -> CreativeOpportunity:
    return CreativeOpportunity(
        id="opp",
        blueprint_id="bp",
        rationale="热点上升 + 角度空白",
        target_platform="douyin",
        target_language="zh-CN",
        created_at=_T0,
    )


def _source_transcript(text: str, lang: str = "zh-CN") -> Transcript:
    return Transcript(
        id="tr",
        language=lang,
        segments=[
            TranscriptSegment(
                id="seg-0", start_ms=0, end_ms=3000, language=lang, text=text, confidence=0.9
            )
        ],
        models=TranscriptModels(asr_provider="asr.x"),
        created_at=_T0,
    )


def test_provider_protocol_conformance() -> None:
    assert isinstance(FakeStructureRewriteProvider(), StructureRewriteProvider)
    assert isinstance(UnconfiguredStructureRewriteProvider(), StructureRewriteProvider)


def test_unconfigured_is_honest() -> None:
    prov = UnconfiguredStructureRewriteProvider()
    table = build_claim_table(
        _blueprint(
            claims=[
                Claim(
                    id="c0",
                    text="事实0",
                    source_status=ClaimSourceStatus.VERIFIED,
                    evidence=[_evidence()],
                )
            ]
        ),
        table_id="ct",
        created_at=_T0,
    )
    tpl = build_beat_template(
        _blueprint(claims=[]), template_id="tpl", created_at=_T0, duration_target_ms=45000
    )
    result = prov.rewrite(
        RewriteRequest(
            script_id="sc", created_at=_T0, language="zh-CN", beat_template=tpl, claim_table=table
        )
    )
    assert result.status is RewriteStatus.UNCONFIGURED
    assert result.error_code is RewriteErrorCode.UNCONFIGURED
    assert result.script is None  # 绝不静默造一个空脚本冒充成功
    assert prov.health_check().status is RewriteStatus.UNCONFIGURED


def test_fake_end_to_end_passes_domain_guardrail() -> None:
    claim = Claim(
        id="claim-a",
        text="该芯片实测能效比上一代提升四成",
        source_status=ClaimSourceStatus.VERIFIED,
        evidence=[_evidence()],
    )
    blueprint = _blueprint(claims=[claim])
    table = build_claim_table(blueprint, table_id="ct", created_at=_T0)
    tpl = build_beat_template(
        blueprint, template_id="tpl", created_at=_T0, duration_target_ms=45000
    )
    brief = build_creative_brief(
        _opportunity(),
        brief_id="b",
        created_at=_T0,
        objective="讲清能效提升",
        audience="AI 从业者",
        angle="实测视角",
        duration_target_ms=45000,
        creation_mode=CreationMode.STRUCTURE_REWRITE,
        claim_table=table,
        must_cover_claim_ids=("claim-a",),
    )
    source = _source_transcript("大家好今天我们来聊聊这颗全新发布的旗舰芯片")

    result = FakeStructureRewriteProvider().rewrite(
        RewriteRequest(
            script_id="sc",
            created_at=_T0,
            language="zh-CN",
            beat_template=tpl,
            claim_table=table,
            brief=brief,
            source_transcript=source,
        )
    )
    assert result.ok and result.script is not None
    script = result.script
    assert script.total_duration_ms == 45000  # 总时长 = 预算
    assert script.brief_id == "b" and script.beat_template_id == "tpl"

    # 核心验收：Fake 产出的脚本直接过纯域护栏（不抄源、引真实事实、合预算、覆盖 must_cover）
    assert validate_script(script, claim_table=table, brief=brief, source_transcript=source) == []
    asserted = {cid for s in script.sentences for cid in s.claim_ids}
    assert "claim-a" in asserted  # must_cover 被真正引用


def test_fake_english_path_valid() -> None:
    claim = Claim(
        id="claim-a",
        text="the chip is 40% more power efficient",
        source_status=ClaimSourceStatus.VERIFIED,
        evidence=[_evidence()],
    )
    blueprint = _blueprint(claims=[claim])
    table = build_claim_table(blueprint, table_id="ct", created_at=_T0)
    tpl = build_beat_template(
        blueprint, template_id="tpl", created_at=_T0, duration_target_ms=40000
    )
    brief = build_creative_brief(
        _opportunity(),
        brief_id="b",
        created_at=_T0,
        objective="explain gains",
        audience="AI builders",
        angle="hands-on",
        duration_target_ms=40000,
        creation_mode=CreationMode.STRUCTURE_REWRITE,
        claim_table=table,
        target_language="en-US",
        must_cover_claim_ids=("claim-a",),
    )
    source = _source_transcript("hey everyone today we unbox the brand new flagship chip", "en-US")
    result = FakeStructureRewriteProvider().rewrite(
        RewriteRequest(
            script_id="sc",
            created_at=_T0,
            language="en-US",
            beat_template=tpl,
            claim_table=table,
            brief=brief,
            source_transcript=source,
        )
    )
    assert result.ok and result.script is not None
    assert result.script.sentences[0].language == "en-US"
    assert (
        validate_script(result.script, claim_table=table, brief=brief, source_transcript=source)
        == []
    )


def test_fake_never_cites_disputed_fact() -> None:
    # 安全属性：即便 brief 强制 must_cover 一个 DISPUTED 事实，Fake 也绝不引用它。
    disputed = Claim(
        id="claim-x",
        text="有争议的性能结论",
        source_status=ClaimSourceStatus.DISPUTED,
        evidence=[_evidence()],
    )
    blueprint = _blueprint(claims=[disputed])
    table = build_claim_table(blueprint, table_id="ct", created_at=_T0)
    tpl = build_beat_template(
        blueprint, template_id="tpl", created_at=_T0, duration_target_ms=45000
    )
    brief = build_creative_brief(
        _opportunity(),
        brief_id="b",
        created_at=_T0,
        objective="o",
        audience="a",
        angle="ang",
        duration_target_ms=45000,
        creation_mode=CreationMode.STRUCTURE_REWRITE,
        claim_table=table,
        must_cover_claim_ids=("claim-x",),
    )
    result = FakeStructureRewriteProvider().rewrite(
        RewriteRequest(
            script_id="sc",
            created_at=_T0,
            language="zh-CN",
            beat_template=tpl,
            claim_table=table,
            brief=brief,
        )
    )
    assert result.ok and result.script is not None
    asserted = {cid for s in result.script.sentences for cid in s.claim_ids}
    assert "claim-x" not in asserted  # 争议事实绝不被自动引用
