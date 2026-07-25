"""结构重写：Beat Template + 语速估算 + 脚本护栏（docs/modules/42 §3）。纯函数。

- build_beat_template：VideoBlueprint 的节拍按 duration_target_ms 等比缩放成 BeatSlot——
  只复用节拍功能 + 时长比，guidance 取 beat.summary（功能抽象），绝不带原句。
- estimate_duration_ms：按语言语速区间（中文字/秒、英文词/秒）估算，非字符粗算（§3.2）。
- validate_script：护栏——不抄源（text_simhash 比对源转录）、事实（引用须在 ClaimTable 且非
  DISPUTED/不可用）、时长（总和≈预算）、禁用词、must_cover 覆盖。

不抄源用 VF-107 的 text_simhash：脚本句与源转录段近乎相同（汉明小）即判抄袭。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    BeatSlot,
    BeatTemplate,
    ClaimSourceStatus,
    ClaimTable,
    CreativeBrief,
    RhetoricalBeatKind,
    ScriptVersion,
    Transcript,
    VideoBlueprint,
)
from videoforge_domain.fingerprints import hamming, text_simhash

_CHARS_PER_SEC_ZH = 5.0  # 中文约 300 字/分
_WORDS_PER_SEC_EN = 2.5  # 英文约 150 词/分
_COPY_MAX_HAMMING = 6  # 与源句 SimHash 汉明 ≤ 此值判抄袭（同 VF-107 同稿阈值区）
_DURATION_TOLERANCE = 0.15  # 时长总和相对预算的容差


def estimate_duration_ms(text: str, language: str) -> int:
    """按语言语速估算一句时长（ms）。中文按非空字符，英文按词。"""
    if language.lower().startswith("zh"):
        units = len([c for c in text if not c.isspace()])
        rate = _CHARS_PER_SEC_ZH
    else:
        units = len(text.split())
        rate = _WORDS_PER_SEC_EN
    if units == 0:
        return 0
    return int(round(units / rate * 1000))


def build_beat_template(
    blueprint: VideoBlueprint, *, template_id: str, created_at: datetime, duration_target_ms: int
) -> BeatTemplate:
    """VideoBlueprint 节拍 → 按目标时长等比缩放的 BeatSlot（只复用功能 + 时长比）。"""
    beats = sorted(blueprint.rhetorical_beats, key=lambda b: b.start_ms)
    if not beats:
        # 无节拍 → 单槽铺满目标时长
        slot = BeatSlot(
            id="slot-0",
            role=RhetoricalBeatKind.UNCLASSIFIED,
            start_ms=0,
            end_ms=duration_target_ms,
            target_duration_ms=duration_target_ms,
        )
        return BeatTemplate(
            id=template_id,
            source_blueprint_id=blueprint.id,
            duration_target_ms=duration_target_ms,
            slots=[slot],
            created_at=created_at,
        )
    source_dur = blueprint.duration_ms
    slots: list[BeatSlot] = []
    cursor = 0
    for i, b in enumerate(beats):
        beat_dur = b.end_ms - b.start_ms
        scaled = round(beat_dur / source_dur * duration_target_ms) if source_dur > 0 else 0
        # 末槽补齐到目标时长，吸收累计取整误差
        if i == len(beats) - 1:
            end = duration_target_ms
        else:
            end = min(cursor + scaled, duration_target_ms)
        end = max(end, cursor)
        slots.append(
            BeatSlot(
                id=f"slot-{i}",
                role=b.kind,
                start_ms=cursor,
                end_ms=end,
                target_duration_ms=end - cursor,
                guidance=b.summary,  # 功能，非原句
            )
        )
        cursor = end
    return BeatTemplate(
        id=template_id,
        source_blueprint_id=blueprint.id,
        duration_target_ms=duration_target_ms,
        slots=slots,
        created_at=created_at,
    )


class ScriptIssueKind(StrEnum):
    EMPTY_SCRIPT = "EMPTY_SCRIPT"
    COPIED_FROM_SOURCE = "COPIED_FROM_SOURCE"
    FACT_NOT_IN_CLAIM_TABLE = "FACT_NOT_IN_CLAIM_TABLE"
    FACT_DISPUTED = "FACT_DISPUTED"
    DURATION_OVER_BUDGET = "DURATION_OVER_BUDGET"
    DURATION_UNDER_BUDGET = "DURATION_UNDER_BUDGET"
    BANNED_PHRASE = "BANNED_PHRASE"
    MUST_COVER_NOT_ASSERTED = "MUST_COVER_NOT_ASSERTED"


@dataclass(frozen=True)
class ScriptIssue:
    kind: ScriptIssueKind
    ref: str
    detail: str


def _normalize(text: str) -> str:
    """归一化：小写 + 去中英文标点 + 折叠空白。

    去标点是抄袭检测的关键：char 3-gram SimHash 对句中插入极敏感，仅在原句里插一个逗号就能
    让汉明距离跳出阈值。先剥除全部标点（Unicode P* 类，覆盖中英文），再在归一化文本上比对与
    计算 SimHash，"照抄原句仅改标点/断句"便无法绕过 COPIED_FROM_SOURCE。
    """
    no_punct = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P"))
    return " ".join(no_punct.lower().split())


def validate_script(
    script: ScriptVersion,
    *,
    claim_table: ClaimTable,
    source_transcript: Transcript | None = None,
    brief: CreativeBrief | None = None,
    copy_max_hamming: int = _COPY_MAX_HAMMING,
    duration_tolerance: float = _DURATION_TOLERANCE,
) -> list[ScriptIssue]:
    """脚本护栏；返回全部违规（空 = 通过）。brief 提供禁用词/must_cover/时长预算。"""
    issues: list[ScriptIssue] = []
    if not script.sentences:
        issues.append(ScriptIssue(ScriptIssueKind.EMPTY_SCRIPT, script.id, "脚本无句子"))
        return issues

    valid_claims = {e.claim_id for e in claim_table.entries}
    blocked_claims = {
        e.claim_id
        for e in claim_table.entries
        if e.fact_status == ClaimSourceStatus.DISPUTED or not e.usable_in_rewrite
    }
    # SimHash 在归一化（去标点）文本上计算，插标点/改断句不改变指纹
    source: list[tuple[str, int]] = []
    if source_transcript is not None:
        for seg in source_transcript.segments:
            seg_norm = _normalize(seg.text)
            source.append((seg_norm, text_simhash(seg_norm)))
    avoid = tuple(brief.avoid) if brief is not None else ()

    for s in script.sentences:
        norm = _normalize(s.text)
        sh = text_simhash(norm)
        for src_norm, src_hash in source:
            if src_norm and (norm == src_norm or hamming(sh, src_hash) <= copy_max_hamming):
                issues.append(ScriptIssue(ScriptIssueKind.COPIED_FROM_SOURCE, s.id, "疑似复用原句"))
                break
        for cid in s.claim_ids:
            if cid not in valid_claims:
                issues.append(ScriptIssue(ScriptIssueKind.FACT_NOT_IN_CLAIM_TABLE, s.id, cid))
            elif cid in blocked_claims:
                issues.append(ScriptIssue(ScriptIssueKind.FACT_DISPUTED, s.id, cid))
        for phrase in avoid:
            if phrase and phrase in s.text:
                issues.append(ScriptIssue(ScriptIssueKind.BANNED_PHRASE, s.id, phrase))

    if brief is not None:
        total = sum(s.target_duration_ms for s in script.sentences)
        budget = brief.duration_target_ms
        if total > budget * (1 + duration_tolerance):
            issues.append(ScriptIssue(ScriptIssueKind.DURATION_OVER_BUDGET, script.id, str(total)))
        elif total < budget * (1 - duration_tolerance):
            issues.append(ScriptIssue(ScriptIssueKind.DURATION_UNDER_BUDGET, script.id, str(total)))
        asserted = {cid for s in script.sentences for cid in s.claim_ids}
        for cid in brief.must_cover_claim_ids:
            if cid not in asserted:
                issues.append(ScriptIssue(ScriptIssueKind.MUST_COVER_NOT_ASSERTED, cid, ""))
    return issues


def is_valid_script(script: ScriptVersion, **kwargs) -> bool:
    return not validate_script(script, **kwargs)
