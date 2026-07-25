"""VF-401 本地化 domain：术语强制 + Claim diff + 时长预算 + 校验护栏。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    CanonicalScript,
    CanonicalSentence,
    ClaimSourceStatus,
    ClaimTable,
    ClaimTableEntry,
    EvidenceSpan,
    Glossary,
    GlossaryEntry,
    LocalizationVariant,
    LocalizedSentence,
    RhetoricalBeatKind,
)
from videoforge_domain import (
    LocalizationIssueKind,
    apply_glossary_preview,
    build_canonical_script,
    compute_claim_diff,
    derive_review_flags,
    estimate_duration_for_language,
    is_valid_localization,
    validate_localization,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _evidence(sid: str = "seg-0") -> EvidenceSpan:
    return EvidenceSpan(kind="transcript", ref_id=sid, start_ms=0, end_ms=1000)


def _table(claims: list[tuple[str, str, ClaimSourceStatus]]) -> ClaimTable:
    return ClaimTable(
        id="ct",
        source_blueprint_id="bp",
        entries=[
            ClaimTableEntry(
                claim_id=cid,
                text=t,
                fact_status=st,
                evidence=[_evidence()],
                confidence=0.9,
                usable_in_rewrite=st is not ClaimSourceStatus.DISPUTED,
            )
            for cid, t, st in claims
        ],
        created_at=_T0,
    )


def _canonical(sents: list[CanonicalSentence]) -> CanonicalScript:
    return CanonicalScript(
        id="cs",
        source_language="zh-CN",
        sentences=sents,
        total_duration_ms=sum(s.target_duration_ms for s in sents),
        created_at=_T0,
    )


def _make_cs(
    sid: str = "cs-0",
    claims: list[str] | None = None,
    must_keep: list[str] | None = None,
    text: str = "端侧模型 20ms 完成推理",
    dur: int = 3000,
) -> CanonicalSentence:
    return CanonicalSentence(
        id=sid,
        beat_slot_id="b",
        role=RhetoricalBeatKind.EVIDENCE,
        source_language="zh-CN",
        source_text=text,
        semantic_intent="evidence",
        claim_ids=claims or [],
        source_time_range_start_ms=0,
        source_time_range_end_ms=dur,
        target_duration_ms=dur,
        must_keep_terms=must_keep or [],
    )


def _make_ls(
    sid: str,
    canonical_id: str,
    text: str,
    dur: int = 3000,
    sim: float = 0.9,
    claims: list[str] | None = None,
    lang: str = "en-US",
) -> LocalizedSentence:
    return LocalizedSentence(
        id=sid,
        canonical_sentence_id=canonical_id,
        target_language=lang,
        text=text,
        duration_estimate_ms=dur,
        semantic_similarity=sim,
        claim_ids=claims or [],
    )


# —— 时长估算 ——


def test_estimate_duration_for_language_matches_rewrite() -> None:
    # 与 domain.estimate_duration_ms 数值一致（同一实现）
    assert estimate_duration_for_language("端侧模型能在 2GB 内存里跑", "zh-CN") > 0
    assert estimate_duration_for_language("On-device model runs on 2 GB", "en-US") > 0


# —— 术语预演 ——


def test_apply_glossary_preview_replaces_and_preserves() -> None:
    gl = Glossary(
        id="g",
        source_language="zh-CN",
        target_language="en-US",
        entries=[
            GlossaryEntry(source_term="端侧", target_term="on-device"),
            GlossaryEntry(source_term="Qwen", target_term="Qwen", preserve_source=True),
        ],
        created_at=_T0,
    )
    out = apply_glossary_preview("Qwen 端侧模型很快", gl)
    assert "on-device" in out and "Qwen" in out  # preserve_source 不动


def test_apply_glossary_preview_longer_terms_first() -> None:
    """'端侧' 优先于 '端'，避免 '端侧' 被拆成 'edge侧'。"""
    gl = Glossary(
        id="g",
        source_language="zh-CN",
        target_language="en-US",
        entries=[
            GlossaryEntry(source_term="端", target_term="edge"),
            GlossaryEntry(source_term="端侧", target_term="on-device"),
        ],
        created_at=_T0,
    )
    assert "on-device" in apply_glossary_preview("端侧模型", gl)


# —— compute_claim_diff ——


def test_claim_diff_empty_when_sets_equal() -> None:
    ct = _table([("c1", "x", ClaimSourceStatus.VERIFIED)])
    diff = compute_claim_diff(["c1"], ["c1"], claim_table=ct)
    assert diff.deltas == []


def test_claim_diff_added_and_removed() -> None:
    ct = _table([("c1", "x", ClaimSourceStatus.VERIFIED), ("c2", "y", ClaimSourceStatus.VERIFIED)])
    diff = compute_claim_diff(["c1"], ["c2"], claim_table=ct)
    kinds = [d.kind for d in diff.deltas]
    assert "ADDED" in kinds and "REMOVED" in kinds


def test_claim_diff_only_set_diff_no_disputed_reporting() -> None:
    """VF-401 verifier finding: compute_claim_diff 只做 set diff，DISPUTED 不再合成
    MUTATED（避免与 validate.DISPUTED_CLAIM_CITED 三重告警）。"""
    ct = _table([("c1", "x", ClaimSourceStatus.DISPUTED)])
    diff = compute_claim_diff(["c1"], ["c1"], claim_table=ct)
    assert diff.deltas == []  # src == loc → 无 delta，与 DISPUTED 状态无关


# —— validate_localization：护栏 ——


def test_validate_empty_variant_fails() -> None:
    canon = _canonical([_make_cs()])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[],
        provider="tra.fake",
        created_at=_T0,
    )
    ct = _table([])
    issues = validate_localization(var, canon, claim_table=ct)
    assert any(i.kind is LocalizationIssueKind.EMPTY_VARIANT for i in issues)


def test_validate_language_mismatch() -> None:
    canon = _canonical([_make_cs()])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "on-device 20 ms", lang="ja-JP")],
        provider="fake",
        created_at=_T0,
    )
    ct = _table([])
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=ct)]
    assert LocalizationIssueKind.LANGUAGE_MISMATCH in kinds


def test_validate_unknown_canonical_id() -> None:
    canon = _canonical([_make_cs()])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-x", "not-there", "x", dur=3000)],
        provider="fake",
        created_at=_T0,
    )
    ct = _table([])
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=ct)]
    assert LocalizationIssueKind.UNKNOWN_CANONICAL_SENTENCE in kinds


def test_validate_must_keep_term_lost() -> None:
    canon = _canonical([_make_cs(must_keep=["Qwen"])])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "the model runs on-device")],
        provider="fake",
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=_table([]))]
    assert LocalizationIssueKind.MUST_KEEP_TERM_LOST in kinds


def test_validate_must_keep_case_insensitive() -> None:
    """must_keep 'AI' 允许 'ai' 出现，且不误伤子串 'brain'。"""
    canon = _canonical([_make_cs(must_keep=["AI"], text="AI 芯片")])
    var_ok = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "an ai chip")],
        provider="fake",
        created_at=_T0,
    )
    kinds_ok = [i.kind for i in validate_localization(var_ok, canon, claim_table=_table([]))]
    assert LocalizationIssueKind.MUST_KEEP_TERM_LOST not in kinds_ok
    # 反例：'brain' 不能命中 'AI'
    var_bad = LocalizationVariant(
        id="v2",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "the brain chip")],
        provider="fake",
        created_at=_T0,
    )
    kinds_bad = [i.kind for i in validate_localization(var_bad, canon, claim_table=_table([]))]
    assert LocalizationIssueKind.MUST_KEEP_TERM_LOST in kinds_bad


def test_validate_glossary_preserve_source_violation() -> None:
    canon = _canonical([_make_cs(text="Qwen 是端侧模型")])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "the model is on-device")],
        provider="fake",
        created_at=_T0,
    )
    gl = Glossary(
        id="g",
        source_language="zh-CN",
        target_language="en-US",
        entries=[GlossaryEntry(source_term="Qwen", target_term="Qwen", preserve_source=True)],
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=_table([]), glossary=gl)]
    assert LocalizationIssueKind.GLOSSARY_VIOLATION in kinds


def test_validate_glossary_preserve_only_when_source_has_it() -> None:
    """源里没有 'Qwen'，即使术语表要求 preserve，也不应对本句判违规。"""
    canon = _canonical([_make_cs(text="端侧模型 20ms")])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "on-device model 20 ms")],
        provider="fake",
        created_at=_T0,
    )
    gl = Glossary(
        id="g",
        source_language="zh-CN",
        target_language="en-US",
        entries=[GlossaryEntry(source_term="Qwen", target_term="Qwen", preserve_source=True)],
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=_table([]), glossary=gl)]
    assert LocalizationIssueKind.GLOSSARY_VIOLATION not in kinds


def test_validate_claim_diff_triggers_review() -> None:
    canon = _canonical([_make_cs(claims=["c1"])])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        # 引用了 c2，源是 c1 → ADDED + REMOVED
        sentences=[_make_ls("ls-0", "cs-0", "on-device runs 20 ms", claims=["c2"])],
        provider="fake",
        created_at=_T0,
    )
    ct = _table([("c1", "x", ClaimSourceStatus.VERIFIED), ("c2", "y", ClaimSourceStatus.VERIFIED)])
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=ct)]
    assert LocalizationIssueKind.CLAIM_DIFF_REQUIRES_REVIEW in kinds


def test_validate_disputed_claim_flagged_even_when_diff_matches() -> None:
    canon = _canonical([_make_cs(claims=["c1"])])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "x runs 20 ms", claims=["c1"])],
        provider="fake",
        created_at=_T0,
    )
    ct = _table([("c1", "x", ClaimSourceStatus.DISPUTED)])
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=ct)]
    assert LocalizationIssueKind.DISPUTED_CLAIM_CITED in kinds


def test_validate_low_semantic_similarity_flagged() -> None:
    canon = _canonical([_make_cs()])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "on-device 20 ms", sim=0.5)],
        provider="fake",
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=_table([]))]
    assert LocalizationIssueKind.LOW_SEMANTIC_SIMILARITY in kinds


def test_validate_duration_out_of_tolerance() -> None:
    canon = _canonical([_make_cs(dur=3000)])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "x", dur=6000)],  # +100% > 15%
        provider="fake",
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=_table([]))]
    assert LocalizationIssueKind.DURATION_OUT_OF_TOLERANCE in kinds


def test_is_valid_localization_true_on_clean() -> None:
    canon = _canonical([_make_cs(claims=["c1"], must_keep=["Qwen"], text="Qwen 端侧模型")])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[
            _make_ls(
                "ls-0",
                "cs-0",
                "the Qwen on-device model runs fast",
                claims=["c1"],
                dur=3000,
                sim=0.92,
            )
        ],
        provider="fake",
        created_at=_T0,
    )
    ct = _table([("c1", "x", ClaimSourceStatus.VERIFIED)])
    assert is_valid_localization(var, canon, claim_table=ct)


def test_derive_review_flags_per_sentence() -> None:
    canon = _canonical([_make_cs(claims=["c1"], must_keep=["Qwen"])])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        # must_keep 丢失 + 低相似度 → 两条 flag
        sentences=[_make_ls("ls-0", "cs-0", "on-device 20ms", claims=["c1"], sim=0.5)],
        provider="fake",
        created_at=_T0,
    )
    ct = _table([("c1", "x", ClaimSourceStatus.VERIFIED)])
    flags = derive_review_flags(var, canon, claim_table=ct)
    assert set(flags["ls-0"]) >= {
        LocalizationIssueKind.MUST_KEEP_TERM_LOST.value,
        LocalizationIssueKind.LOW_SEMANTIC_SIMILARITY.value,
    }


# —— build_canonical_script ——


def test_build_canonical_from_script_uses_transcript_ids_when_present() -> None:
    from videoforge_contracts import (
        ScriptSentence,
        ScriptVersion,
        Transcript,
        TranscriptModels,
        TranscriptSegment,
    )

    tr = Transcript(
        id="tr",
        language="zh-CN",
        duration_ms=10000,
        segments=[
            TranscriptSegment(
                id="s0", start_ms=0, end_ms=4000, language="zh-CN", text="端侧模型", confidence=0.9
            ),
            TranscriptSegment(
                id="s1",
                start_ms=4000,
                end_ms=10000,
                language="zh-CN",
                text="推理 20ms",
                confidence=0.9,
            ),
        ],
        models=TranscriptModels(asr_provider="fake"),
        created_at=_T0,
    )
    script = ScriptVersion(
        id="sv",
        language="zh-CN",
        version=1,
        sentences=[
            ScriptSentence(
                id="s0",
                beat_slot_id="b",
                role=RhetoricalBeatKind.HOOK,
                text="端侧模型登场",
                target_duration_ms=4000,
                claim_ids=["c1"],
                language="zh-CN",
            ),
            ScriptSentence(
                id="s1",
                beat_slot_id="b",
                role=RhetoricalBeatKind.EVIDENCE,
                text="20ms 完成推理",
                target_duration_ms=6000,
                claim_ids=["c1"],
                language="zh-CN",
            ),
        ],
        created_at=_T0,
    )
    canon = build_canonical_script(
        script,
        claim_table=_table([("c1", "x", ClaimSourceStatus.VERIFIED)]),
        canonical_id="c-1",
        created_at=_T0,
        source_transcript=tr,
        must_keep_by_sentence={"s1": ["20ms"]},
    )
    assert canon.sentences[0].source_time_range_start_ms == 0
    assert canon.sentences[0].source_time_range_end_ms == 4000
    assert canon.sentences[1].source_time_range_end_ms == 10000
    assert canon.sentences[1].must_keep_terms == ["20ms"]


def test_build_canonical_falls_back_to_cursor_when_no_transcript() -> None:
    from videoforge_contracts import ScriptSentence, ScriptVersion

    script = ScriptVersion(
        id="sv",
        language="zh-CN",
        version=1,
        sentences=[
            ScriptSentence(
                id="a",
                beat_slot_id="b",
                role=RhetoricalBeatKind.HOOK,
                text="x",
                target_duration_ms=2000,
                language="zh-CN",
            ),
            ScriptSentence(
                id="b",
                beat_slot_id="b",
                role=RhetoricalBeatKind.CTA,
                text="y",
                target_duration_ms=3000,
                language="zh-CN",
            ),
        ],
        created_at=_T0,
    )
    canon = build_canonical_script(
        script, claim_table=_table([]), canonical_id="c-1", created_at=_T0
    )
    assert canon.sentences[0].source_time_range_start_ms == 0
    assert canon.sentences[0].source_time_range_end_ms == 2000
    assert canon.sentences[1].source_time_range_start_ms == 2000
    assert canon.sentences[1].source_time_range_end_ms == 5000


# —— 边界防护 ——


def test_validate_sentence_mismatch_missing_translation() -> None:
    """verifier REFUTED：canonical 有句但 variant 漏译整句 → 必须报 SENTENCE_MISMATCH。"""
    s0 = _make_cs("cs-0", claims=["c1"])
    s1 = _make_cs("cs-1", claims=["c2"])
    canon = _canonical([s0, s1])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        # 只译了 s0，漏了 s1
        sentences=[_make_ls("ls-0", "cs-0", "x runs 20 ms", claims=["c1"])],
        provider="fake",
        created_at=_T0,
    )
    ct = _table([("c1", "x", ClaimSourceStatus.VERIFIED), ("c2", "y", ClaimSourceStatus.VERIFIED)])
    issues = validate_localization(var, canon, claim_table=ct)
    kinds = [i.kind for i in issues]
    assert LocalizationIssueKind.SENTENCE_MISMATCH in kinds
    # 具体指向 cs-1
    mismatches = [i for i in issues if i.kind is LocalizationIssueKind.SENTENCE_MISMATCH]
    assert any(m.ref == "cs-1" for m in mismatches)


def test_validate_sentence_mismatch_duplicate_reference() -> None:
    """同一 canonical id 被 variant 引用两次 → SENTENCE_MISMATCH（重复）。"""
    canon = _canonical([_make_cs("cs-0")])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[
            _make_ls("ls-a", "cs-0", "on-device 20 ms"),
            _make_ls("ls-b", "cs-0", "device runs 20 ms"),  # 同 canonical id
        ],
        provider="fake",
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=_table([]))]
    assert LocalizationIssueKind.SENTENCE_MISMATCH in kinds


def test_must_keep_ai_between_cjk_matches() -> None:
    """verifier finding: '这是AI芯片' 里的 'AI' 应命中 must_keep（CJK 相邻不算 word 字符）。"""
    canon = _canonical([_make_cs(text="AI 芯片", must_keep=["AI"])])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="zh-CN",
        sentences=[_make_ls("ls-0", "cs-0", "这是AI芯片", lang="zh-CN")],
        provider="fake",
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=_table([]))]
    assert LocalizationIssueKind.MUST_KEEP_TERM_LOST not in kinds


def test_validate_target_duration_zero_skips_ratio_check() -> None:
    """canon.target_duration_ms == 0 → 不算超容差（避免 div-by-zero）。"""
    canon = _canonical([_make_cs(dur=0)])
    var = LocalizationVariant(
        id="v",
        canonical_script_id="cs",
        target_language="en-US",
        sentences=[_make_ls("ls-0", "cs-0", "x", dur=1000)],
        provider="fake",
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_localization(var, canon, claim_table=_table([]))]
    assert LocalizationIssueKind.DURATION_OUT_OF_TOLERANCE not in kinds
