"""Beat Template 缩放 + 语速估算 + 脚本护栏：不抄源/事实/时长/禁用词/must_cover。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    ClaimSourceStatus,
    ClaimTable,
    ClaimTableEntry,
    CreationMode,
    CreativeBrief,
    EvidenceSpan,
    RhetoricalBeat,
    RhetoricalBeatKind,
    ScriptSentence,
    ScriptVersion,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
    VideoBlueprint,
)
from videoforge_domain import (
    ScriptIssueKind,
    build_beat_template,
    estimate_duration_ms,
    is_valid_script,
    validate_script,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


# —— 语速估算 ——

def test_estimate_duration_zh_by_chars() -> None:
    # 中文按字：7 字 / 5字每秒 ≈ 1400ms（非字符粗算，忽略空白）
    assert estimate_duration_ms("今天带大家拆解", "zh-CN") == 1400


def test_estimate_duration_en_by_words() -> None:
    # 英文按词：4 词 / 2.5词每秒 = 1600ms
    assert estimate_duration_ms("welcome to the demo", "en-US") == 1600


def test_estimate_empty_is_zero() -> None:
    assert estimate_duration_ms("", "zh-CN") == 0


# —— Beat Template 缩放 ——

def _blueprint(beats, dur=10000) -> VideoBlueprint:
    return VideoBlueprint(id="bp", duration_ms=dur, rhetorical_beats=beats, created_at=_T0)


def test_template_scales_to_target_and_keeps_functions() -> None:
    bp = _blueprint([
        RhetoricalBeat(id="r0", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=2000,
                       summary="钩子"),
        RhetoricalBeat(id="r1", kind=RhetoricalBeatKind.EVIDENCE, start_ms=2000, end_ms=10000,
                       summary="证据"),
    ], dur=10000)
    t = build_beat_template(bp, template_id="tpl", created_at=_T0, duration_target_ms=45000)
    assert t.slots[0].start_ms == 0 and t.slots[-1].end_ms == 45000  # 铺满目标时长
    for a, b in zip(t.slots, t.slots[1:], strict=False):
        assert a.end_ms == b.start_ms  # 无缝
    assert t.slots[0].role is RhetoricalBeatKind.HOOK
    assert t.slots[0].guidance == "钩子"  # 只带功能，不带原句
    # 比例保持：HOOK 2/10 → 约 9000ms
    assert abs(t.slots[0].target_duration_ms - 9000) < 50


def test_template_no_beats_single_slot() -> None:
    t = build_beat_template(_blueprint([]), template_id="tpl", created_at=_T0,
                            duration_target_ms=30000)
    assert len(t.slots) == 1 and t.slots[0].end_ms == 30000


# —— 脚本护栏 ——

def _table(*claims) -> ClaimTable:
    return ClaimTable(id="ct", entries=list(claims), created_at=_T0)


def _entry(cid, status=ClaimSourceStatus.VERIFIED, usable=True) -> ClaimTableEntry:
    return ClaimTableEntry(
        claim_id=cid, text=f"事实-{cid}", fact_status=status, usable_in_rewrite=usable,
        evidence=[EvidenceSpan(kind="transcript", ref_id="seg-0", start_ms=0, end_ms=1000)],
    )


def _sentence(sid, text, dur, claims=()) -> ScriptSentence:
    return ScriptSentence(
        id=sid, beat_slot_id="slot-0", role=RhetoricalBeatKind.EVIDENCE, text=text,
        target_duration_ms=dur, claim_ids=list(claims), language="zh-CN",
    )


def _script(sentences) -> ScriptVersion:
    return ScriptVersion(id="sc", language="zh-CN", sentences=sentences, created_at=_T0)


def _brief(*, avoid=(), must_cover=(), budget=10000) -> CreativeBrief:
    return CreativeBrief(
        id="b", objective="o", audience="a", platform="douyin", target_language="zh-CN",
        duration_target_ms=budget, creation_mode=CreationMode.STRUCTURE_REWRITE, angle="ang",
        avoid=list(avoid), must_cover_claim_ids=list(must_cover), created_at=_T0,
    )


def _source(text) -> Transcript:
    return Transcript(
        id="tr", language="zh-CN",
        segments=[TranscriptSegment(id="seg-0", start_ms=0, end_ms=2000, language="zh-CN",
                                    text=text, confidence=0.9)],
        models=TranscriptModels(asr_provider="asr.x"), created_at=_T0,
    )


def test_valid_script_passes() -> None:
    table = _table(_entry("c0"))
    script = _script([_sentence("s0", "用中性表述展开这一段", 10000, claims=["c0"])])
    brief = _brief(must_cover=("c0",), budget=10000)
    assert validate_script(script, claim_table=table, brief=brief,
                           source_transcript=_source("完全不同的原始转录内容")) == []
    assert is_valid_script(script, claim_table=table, brief=brief)


def test_copied_from_source_detected() -> None:
    table = _table(_entry("c0"))
    src_text = "今天带大家拆解这款全新的 AI 芯片产品"
    script = _script([_sentence("s0", src_text, 10000)])  # 逐字照抄源句
    issues = validate_script(script, claim_table=table, source_transcript=_source(src_text))
    assert ScriptIssueKind.COPIED_FROM_SOURCE in {i.kind for i in issues}


def test_copied_detected_despite_punctuation_laundering_zh() -> None:
    # 回归：照抄原句仅插标点/改断句不得绕过抄袭检测（verifier 复现的假阴性）。
    table = _table(_entry("c0"))
    src = "这颗芯片的能效比上一代提升了整整四成非常夸张"
    laundered = "这颗芯片的能效比上一代提升了整整四成，非常夸张！"  # 同字，仅插全角逗号+感叹号
    script = _script([_sentence("s0", laundered, 10000)])
    issues = validate_script(script, claim_table=table, source_transcript=_source(src))
    assert ScriptIssueKind.COPIED_FROM_SOURCE in {i.kind for i in issues}


def test_copied_detected_despite_punctuation_laundering_en() -> None:
    table = _table(_entry("c0"))
    src = "today we are going to unbox the brand new flagship chip and test it"
    laundered = "today, we are going to unbox the brand new flagship chip and test it"
    script = ScriptVersion(
        id="sc", language="en-US",
        sentences=[ScriptSentence(id="s0", beat_slot_id="slot-0",
                                  role=RhetoricalBeatKind.EVIDENCE, text=laundered,
                                  target_duration_ms=10000, language="en-US")],
        created_at=_T0,
    )
    src_tr = Transcript(
        id="tr", language="en-US",
        segments=[TranscriptSegment(id="seg-0", start_ms=0, end_ms=2000, language="en-US",
                                    text=src, confidence=0.9)],
        models=TranscriptModels(asr_provider="asr.x"), created_at=_T0,
    )
    issues = validate_script(script, claim_table=table, source_transcript=src_tr)
    assert ScriptIssueKind.COPIED_FROM_SOURCE in {i.kind for i in issues}


def test_fact_not_in_table_and_disputed() -> None:
    table = _table(_entry("c0"), _entry("c1", status=ClaimSourceStatus.DISPUTED, usable=False))
    script = _script([
        _sentence("s0", "引用了不存在的事实", 5000, claims=["ghost"]),
        _sentence("s1", "引用了有争议的事实", 5000, claims=["c1"]),
    ])
    kinds = {i.kind for i in validate_script(script, claim_table=table)}
    assert ScriptIssueKind.FACT_NOT_IN_CLAIM_TABLE in kinds
    assert ScriptIssueKind.FACT_DISPUTED in kinds


def test_duration_over_and_under_budget() -> None:
    table = _table(_entry("c0"))
    over = _script([_sentence("s0", "太长了", 20000)])
    under = _script([_sentence("s0", "太短了", 1000)])
    brief = _brief(budget=10000)
    over_kinds = {i.kind for i in validate_script(over, claim_table=table, brief=brief)}
    under_kinds = {i.kind for i in validate_script(under, claim_table=table, brief=brief)}
    assert ScriptIssueKind.DURATION_OVER_BUDGET in over_kinds
    assert ScriptIssueKind.DURATION_UNDER_BUDGET in under_kinds


def test_banned_phrase_detected() -> None:
    table = _table(_entry("c0"))
    script = _script([_sentence("s0", "这里照抄原标题很省事", 10000)])
    brief = _brief(avoid=("照抄原标题",), budget=10000)
    kinds = {i.kind for i in validate_script(script, claim_table=table, brief=brief)}
    assert ScriptIssueKind.BANNED_PHRASE in kinds


def test_must_cover_not_asserted_detected() -> None:
    table = _table(_entry("c0"))
    script = _script([_sentence("s0", "没有引用任何事实", 10000)])
    brief = _brief(must_cover=("c0",), budget=10000)
    kinds = {i.kind for i in validate_script(script, claim_table=table, brief=brief)}
    assert ScriptIssueKind.MUST_COVER_NOT_ASSERTED in kinds


def test_empty_script_detected() -> None:
    kinds = {i.kind for i in validate_script(_script([]), claim_table=_table())}
    assert ScriptIssueKind.EMPTY_SCRIPT in kinds
