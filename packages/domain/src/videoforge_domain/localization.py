"""本地化：术语强制 + Claim diff + 时长预算 + 校验护栏（docs/modules/43 §3-§4）。纯函数。

- apply_glossary_check：不改译文，只报告哪些 must_keep 术语未按术语表落地（provider 该改译）。
- build_canonical_script：ScriptVersion + ClaimTable → 中性稿（语言无关；每句带 must_keep_terms）。
- compute_claim_diff：源 vs 本地化 Claim 引用的结构化差异（漏译/添加事实）。
- validate_localization：护栏——Claim diff 非空必须审核、术语失守、低语义相似度、超时长预算。
  返回 typed LocalizationIssue（空 = 通过），并可派生 needs_review + review_reasons。

术语强制的边界：术语替换是 provider 的职责（含语法整合）；domain 只负责**审计**——
避免"暴力字符串替换破坏语法"的坑（"端侧" 直译 "on-device" 需要重排句子）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    CanonicalScript,
    CanonicalSentence,
    ClaimDelta,
    ClaimDiff,
    ClaimSourceStatus,
    ClaimTable,
    Glossary,
    LocalizationVariant,
    ScriptVersion,
    Transcript,
)
from videoforge_domain.rewrite import estimate_duration_ms

_DEFAULT_SIMILARITY_FLOOR = 0.75  # <此值即触发审核
_DEFAULT_DURATION_TOLERANCE = 0.15  # 单句时长相对预算的容差


class LocalizationIssueKind(StrEnum):
    EMPTY_VARIANT = "EMPTY_VARIANT"
    SENTENCE_MISMATCH = "SENTENCE_MISMATCH"  # variant 句与 canonical 不 1:1 对应
    UNKNOWN_CANONICAL_SENTENCE = "UNKNOWN_CANONICAL_SENTENCE"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"  # sentence.target_language ≠ variant.target_language
    MUST_KEEP_TERM_LOST = "MUST_KEEP_TERM_LOST"
    GLOSSARY_VIOLATION = "GLOSSARY_VIOLATION"  # preserve_source 术语被译走
    CLAIM_DIFF_REQUIRES_REVIEW = "CLAIM_DIFF_REQUIRES_REVIEW"
    DISPUTED_CLAIM_CITED = "DISPUTED_CLAIM_CITED"
    LOW_SEMANTIC_SIMILARITY = "LOW_SEMANTIC_SIMILARITY"
    DURATION_OUT_OF_TOLERANCE = "DURATION_OUT_OF_TOLERANCE"


@dataclass(frozen=True)
class LocalizationIssue:
    kind: LocalizationIssueKind
    ref: str  # sentence id 或 variant id
    detail: str


def build_canonical_script(
    script: ScriptVersion,
    *,
    claim_table: ClaimTable,
    canonical_id: str,
    created_at: datetime,
    source_transcript: Transcript | None = None,
    must_keep_by_sentence: dict[str, list[str]] | None = None,
    speaker_by_sentence: dict[str, str] | None = None,
) -> CanonicalScript:
    """ScriptVersion（VF-302）+ ClaimTable → 中性稿。

    每句的 must_keep_terms 由调用方提供（通常从 brief.avoid 反面/术语表派生），
    speaker_id 亦然。target_duration_ms 沿用脚本自身的估算（VF-302 已用 estimate_duration_ms）。
    source_time_range 若给 transcript 就用第一句 seg 边界，否则从 script 累加估算。
    """
    must_keep = must_keep_by_sentence or {}
    speakers = speaker_by_sentence or {}
    seg_ends_by_id: dict[str, tuple[int, int]] = {}
    if source_transcript is not None:
        for seg in source_transcript.segments:
            seg_ends_by_id[seg.id] = (seg.start_ms, seg.end_ms)
    sentences: list[CanonicalSentence] = []
    cursor = 0
    for s in script.sentences:
        # 时间范围：若能从 transcript 找到相同 id 就用；否则按估算时长顺序拼接
        if s.id in seg_ends_by_id:
            start_ms, end_ms = seg_ends_by_id[s.id]
        else:
            start_ms = cursor
            end_ms = cursor + s.target_duration_ms
            cursor = end_ms
        sentences.append(CanonicalSentence(
            id=s.id, beat_slot_id=s.beat_slot_id, role=s.role,
            speaker_id=speakers.get(s.id),
            source_language=script.language,
            source_text=s.text,
            semantic_intent=f"role={s.role.value}",
            claim_ids=list(s.claim_ids),
            source_time_range_start_ms=start_ms,
            source_time_range_end_ms=end_ms,
            target_duration_ms=s.target_duration_ms,
            must_keep_terms=list(must_keep.get(s.id, [])),
        ))
    total = script.total_duration_ms or sum(s.target_duration_ms for s in sentences)
    return CanonicalScript(
        id=canonical_id, script_version_id=script.id,
        source_language=script.language, sentences=sentences,
        total_duration_ms=total, created_at=created_at,
    )


def compute_claim_diff(
    source_claim_ids: list[str],
    localized_claim_ids: list[str],
    *,
    claim_table: ClaimTable | None = None,  # 保留形参用于兼容；DISPUTED 由 validate 处理
) -> ClaimDiff:
    """结构化 Claim 差异——**只做纯 set diff**。ADDED（危险）/REMOVED（漏译）。

    verifier 指出：DISPUTED 引用与 diff 语义正交（"引用未变化"也可能是 DISPUTED），
    把 DISPUTED 塞进 MUTATED 会产生三重告警（MUTATED + CLAIM_DIFF_REQUIRES_REVIEW +
    DISPUTED_CLAIM_CITED）且 MUTATED 标签失真。DISPUTED 现在只由 validate_localization
    的 DISPUTED_CLAIM_CITED 独立报告——单一职责，避免语义混淆。

    MUTATED delta 仍在合同里，供未来 provider 报告"语义变化但引用不变"（如数字漂移）——
    domain 层不合成，只透传 provider 报告的 deltas（当前 Fake 不生成 MUTATED）。
    """
    src = list(dict.fromkeys(source_claim_ids))  # 去重保序
    loc = list(dict.fromkeys(localized_claim_ids))
    src_set, loc_set = set(src), set(loc)
    deltas: list[ClaimDelta] = []
    for cid in loc:
        if cid not in src_set:
            deltas.append(ClaimDelta(
                kind="ADDED", claim_id=cid,
                detail=f"本地化新增 Claim 引用 {cid!r}——需人工核对是否有证据",
            ))
    for cid in src:
        if cid not in loc_set:
            deltas.append(ClaimDelta(
                kind="REMOVED", claim_id=cid,
                detail=f"本地化漏引 Claim {cid!r}——事实可能丢失",
            ))
    return ClaimDiff(source_claim_ids=src, localized_claim_ids=loc, deltas=deltas)


def _is_word_char(ch: str) -> bool:
    """word-boundary 判定：仅 ASCII 字母数字算 word 字符。

    verifier 揭示：`ch.isalnum()` 对 CJK 汉字也返 True——导致 '这是AI芯片' 里 'AI' 的
    两侧 CJK 被当成 word 字符，'AI' 被误判为"某更大 word 的一部分"，术语判定返回 False。
    改为仅 ASCII alnum 计入 word 字符，中英混排时 'AI' 相邻 CJK 仍算独立术语命中。
    """
    return ch.isascii() and (ch.isalnum() or ch == "_")


def _text_contains_term(text: str, term: str) -> bool:
    """术语出现检测——大小写不敏感。对含 ASCII 字母的术语用 word-boundary 近似避免子串误伤
    （'AI' 不应在 'brain' 中命中；但 'AI' 应在 '这是AI芯片' 中命中——两侧 CJK 不算 word 字符）。
    纯 CJK 术语按包含判断。
    """
    if not term:
        return True
    text_low = text.lower()
    term_low = term.lower()
    if any(_is_word_char(c) for c in term):
        # 用（仅 ASCII 的）word-boundary 近似
        padded = f" {text_low} "
        idx = 0
        while True:
            idx = padded.find(term_low, idx)
            if idx < 0:
                return False
            left = padded[idx - 1]
            right = padded[idx + len(term_low)]
            if not (_is_word_char(left) or _is_word_char(right)):
                return True
            idx += 1
    return term_low in text_low


def _apply_glossary_replacement_preview(text: str, glossary: Glossary) -> str:
    """预演一次术语表替换（不含语法整合），仅供 audit 提示；生产由 provider 负责。"""
    result = text
    # 长术语优先，避免 "端" 覆盖 "端侧"
    entries = sorted(glossary.entries, key=lambda e: -len(e.source_term))
    for e in entries:
        if e.preserve_source:
            continue
        # case-insensitive 简易替换：仅处理精确匹配（不做词形/时态）
        low = result.lower()
        src_low = e.source_term.lower()
        idx = 0
        rebuilt: list[str] = []
        prev = 0
        while True:
            k = low.find(src_low, idx)
            if k < 0:
                rebuilt.append(result[prev:])
                break
            rebuilt.append(result[prev:k])
            rebuilt.append(e.target_term)
            idx = k + len(src_low)
            prev = idx
        result = "".join(rebuilt)
    return result


def validate_localization(
    variant: LocalizationVariant,
    canonical: CanonicalScript,
    *,
    claim_table: ClaimTable,
    glossary: Glossary | None = None,
    similarity_floor: float = _DEFAULT_SIMILARITY_FLOOR,
    duration_tolerance: float = _DEFAULT_DURATION_TOLERANCE,
) -> list[LocalizationIssue]:
    """本地化护栏；返回全部违规（空 = 通过）。"""
    issues: list[LocalizationIssue] = []
    if not variant.sentences:
        issues.append(LocalizationIssue(
            LocalizationIssueKind.EMPTY_VARIANT, variant.id, "本地化产物无句子"))
        return issues
    canon_by_id = {c.id: c for c in canonical.sentences}
    # SENTENCE_MISMATCH：canonical 每句必须被 variant 覆盖一次且仅一次（§4.3 漏译必审）。
    # verifier 揭示：光看逐句校验，variant 漏掉整句 (含 Claim) 会静默通过——是真空区。
    covered: dict[str, int] = {}
    for ls in variant.sentences:
        covered[ls.canonical_sentence_id] = covered.get(ls.canonical_sentence_id, 0) + 1
    for canon in canonical.sentences:
        count = covered.get(canon.id, 0)
        if count == 0:
            issues.append(LocalizationIssue(
                LocalizationIssueKind.SENTENCE_MISMATCH, canon.id,
                f"canonical 句 {canon.id!r} 未在 variant 中出现（漏译）",
            ))
        elif count > 1:
            issues.append(LocalizationIssue(
                LocalizationIssueKind.SENTENCE_MISMATCH, canon.id,
                f"canonical 句 {canon.id!r} 被 variant 引用 {count} 次（重复）",
            ))
    # 逐句校验
    for ls in variant.sentences:
        if ls.canonical_sentence_id not in canon_by_id:
            issues.append(LocalizationIssue(
                LocalizationIssueKind.UNKNOWN_CANONICAL_SENTENCE, ls.id,
                f"canonical_sentence_id {ls.canonical_sentence_id!r} 不在 canonical",
            ))
            continue
        canon = canon_by_id[ls.canonical_sentence_id]
        if ls.target_language != variant.target_language:
            issues.append(LocalizationIssue(
                LocalizationIssueKind.LANGUAGE_MISMATCH, ls.id,
                f"sentence.target_language={ls.target_language} ≠ "
                f"variant.target_language={variant.target_language}",
            ))
        # must_keep_terms：术语必须原样保留（大小写不敏感）
        for term in canon.must_keep_terms:
            if not _text_contains_term(ls.text, term):
                issues.append(LocalizationIssue(
                    LocalizationIssueKind.MUST_KEEP_TERM_LOST, ls.id,
                    f"must_keep 术语 {term!r} 未在译文出现",
                ))
        # 术语表 preserve_source 条目：译文里不该出现 target 但缺失 source
        if glossary is not None:
            for e in glossary.entries:
                if not e.preserve_source:
                    continue
                # preserve_source 即目标必须原样保留 source_term
                # 只在源含此术语时才要求译文保留（否则会把无关句判违规）
                if _text_contains_term(canon.source_text, e.source_term) and \
                   not _text_contains_term(ls.text, e.source_term):
                    issues.append(LocalizationIssue(
                        LocalizationIssueKind.GLOSSARY_VIOLATION, ls.id,
                        f"术语表要求原样保留 {e.source_term!r}，译文未含",
                    ))
        # Claim diff
        cd = compute_claim_diff(canon.claim_ids, ls.claim_ids, claim_table=claim_table)
        if cd.deltas:
            issues.append(LocalizationIssue(
                LocalizationIssueKind.CLAIM_DIFF_REQUIRES_REVIEW, ls.id,
                f"{len(cd.deltas)} 条 Claim 差异需人工审核",
            ))
        # DISPUTED 单独强调
        entries_by_id = {e.claim_id: e for e in claim_table.entries}
        for cid in ls.claim_ids:
            entry = entries_by_id.get(cid)
            if entry is not None and entry.fact_status is ClaimSourceStatus.DISPUTED:
                issues.append(LocalizationIssue(
                    LocalizationIssueKind.DISPUTED_CLAIM_CITED, ls.id,
                    f"引用 DISPUTED Claim {cid!r}——发布前必须人工确认",
                ))
        # 语义相似度
        if ls.semantic_similarity < similarity_floor:
            issues.append(LocalizationIssue(
                LocalizationIssueKind.LOW_SEMANTIC_SIMILARITY, ls.id,
                f"semantic_similarity={ls.semantic_similarity:.2f} < {similarity_floor:.2f}",
            ))
        # 时长预算：允许 canon 目标时长 ± tolerance
        target = canon.target_duration_ms
        if target > 0:
            ratio = ls.duration_estimate_ms / target
            low = 1 - duration_tolerance
            high = 1 + duration_tolerance
            if ratio < low or ratio > high:
                issues.append(LocalizationIssue(
                    LocalizationIssueKind.DURATION_OUT_OF_TOLERANCE, ls.id,
                    f"duration_estimate {ls.duration_estimate_ms}ms 相对目标 {target}ms "
                    f"偏差 {(ratio - 1):+.0%} 超容差 ±{int(duration_tolerance * 100)}%",
                ))
    return issues


def is_valid_localization(
    variant: LocalizationVariant,
    canonical: CanonicalScript,
    *,
    claim_table: ClaimTable,
    glossary: Glossary | None = None,
) -> bool:
    return not validate_localization(
        variant, canonical, claim_table=claim_table, glossary=glossary,
    )


def derive_review_flags(
    variant: LocalizationVariant,
    canonical: CanonicalScript,
    *,
    claim_table: ClaimTable,
    glossary: Glossary | None = None,
) -> dict[str, list[str]]:
    """按句聚合 review_reasons（issue.kind 值），供上层置 LocalizedSentence.needs_review。"""
    result: dict[str, list[str]] = {}
    for issue in validate_localization(
        variant, canonical, claim_table=claim_table, glossary=glossary,
    ):
        result.setdefault(issue.ref, []).append(issue.kind.value)
    return result


def estimate_duration_for_language(text: str, language: str) -> int:
    """本地化的时长估算——直接复用 VF-302 的 estimate_duration_ms（同语速表）。"""
    return estimate_duration_ms(text, language)


def apply_glossary_preview(text: str, glossary: Glossary) -> str:
    """便捷入口：预演术语替换（不改语法），仅供 UI 提示或测试对比。"""
    return _apply_glossary_replacement_preview(text, glossary)
