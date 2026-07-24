"""本地化审核：语言 QA 聚合 + 句级批准 + 局部重跑（docs/modules/43 §12-§13）。纯函数。

- §12 纯一致性检查：`check_number_consistency`（源/目标数字一致，§13 "数字一致率 100%"）、
  `check_negation_consistency`（否定标记数对齐，启发式）。
- `aggregate_localization_qa` 把各层发现装配成逐句 QA 报告；`validate_localization_publish_gate`
  是发布门（BLOCKER → 拦；MAJOR 超阈 → 拦）。
- **`compute_rerun_scope`（§13 headline）**：改单句译文 → 只重跑**该句** TTS/字幕/口型 +
  下游渲染；其它句零波及（返回 `unaffected_sentence_ids` 作为作用域证明）。
- `sentence_review_queue` / `validate_localization_review`：句级批准队列 + 护栏
  （不能批准仍带 BLOCKER 的句）。

**红线**：数字丢失/篡改是 BLOCKER（§13 事实一致）；发布门绝不放行带 BLOCKER 的变体；
改单句的重跑作用域绝不触碰其它句的上游（TTS/字幕/口型/翻译）。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    LocalizationQACheck,
    LocalizationQAFinding,
    LocalizationQAReport,
    LocalizationReview,
    QASeverity,
    ReRunStage,
    ReviewState,
)

# 数字 token：整数/小数/千分位（1,000 / 3.5 / 120）
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
# 否定标记（源/目标语言各扫）
_ZH_NEGATION = ("不", "没", "無", "无", "别", "非", "未", "勿", "莫")
_EN_NEGATION_RE = re.compile(
    r"\b(?:not|no|never|none|without|cannot|can't|won't|don't|doesn't|"
    r"didn't|isn't|aren't|wasn't|weren't|n't)\b",
    re.IGNORECASE,
)

# 发布门：MAJOR 超过此数即从 report-only 升级为 BLOCK（与 VF-309 一致）
DEFAULT_MAX_MAJOR_BEFORE_BLOCK = 3


class ReRunEditKind(StrEnum):
    """触发局部重跑的编辑类型。"""

    TEXT_EDIT = "TEXT_EDIT"  # 改译文（§13 主用例）
    VOICE_CHANGE = "VOICE_CHANGE"  # 换声/Voice Profile
    TIMING_CHANGE = "TIMING_CHANGE"  # 只调目标时长/语速


class LocalizationReviewIssueKind(StrEnum):
    APPROVED_OVER_BLOCKER = "APPROVED_OVER_BLOCKER"  # 批准了仍带 BLOCKER 的句
    DECISION_FOR_UNKNOWN_SENTENCE = "DECISION_FOR_UNKNOWN_SENTENCE"


@dataclass(frozen=True)
class LocalizationReviewIssue:
    kind: LocalizationReviewIssueKind
    ref: str
    detail: str


@dataclass(frozen=True)
class ReRunScope:
    """§13 局部重跑作用域。

    - `per_sentence_stages`：**只**含被编辑句，每句要重跑的阶段。
    - `global_stages`：一次性下游（音频合成 + 渲染）。
    - `unaffected_sentence_ids`：未被波及的句（作用域证明——它们零重跑）。
    """

    edit_kind: ReRunEditKind
    edited_sentence_ids: tuple[str, ...]
    per_sentence_stages: dict[str, tuple[ReRunStage, ...]]
    global_stages: tuple[ReRunStage, ...]
    unaffected_sentence_ids: tuple[str, ...]


def _numbers(text: str) -> list[str]:
    """抽取并归一化数字（去千分位逗号）。返回多重集（保留重复）。"""
    out: list[str] = []
    for tok in _NUMBER_RE.findall(text):
        out.append(tok.replace(",", ""))
    return sorted(out)


def check_number_consistency(
    sentence_id: str, source: str, target: str,
) -> LocalizationQAFinding | None:
    """源/目标数字多重集必须一致（VF-401 术语表锁定数值/单位；§13 数字一致率 100%）。

    数字丢失/新增/篡改 → BLOCKER。已知局限：数字被写成词（5→five）会误报——业务上数字
    保留为数字，故按 BLOCKER 拦，交人工确认。
    """
    src, tgt = _numbers(source), _numbers(target)
    if src == tgt:
        return None
    only_in_source = sorted(_multiset_diff(src, tgt))  # 源有、译缺（漏译数字）
    only_in_target = sorted(_multiset_diff(tgt, src))  # 译有、源无（凭空数字）
    return LocalizationQAFinding(
        sentence_id=sentence_id,
        check=LocalizationQACheck.NUMBER_CONSISTENCY,
        severity=QASeverity.BLOCKER,
        detail=f"数字不一致：源有译无={only_in_source} 译有源无={only_in_target}",
        evidence={"source_numbers": src, "target_numbers": tgt},
    )


def _multiset_diff(a: list[str], b: list[str]) -> list[str]:
    """a 中有、b 中不足的元素（多重集差）。"""
    diff = Counter(a) - Counter(b)
    return list(diff.elements())


def _count_negations(text: str, lang: str) -> int:
    if lang.lower().startswith("zh"):
        return sum(text.count(m) for m in _ZH_NEGATION)
    return len(_EN_NEGATION_RE.findall(text))


def check_negation_consistency(
    sentence_id: str, source: str, target: str,
    *, source_lang: str, target_lang: str,
) -> LocalizationQAFinding | None:
    """否定标记数对齐（启发式）。数目不等 → MAJOR（可能漏译/加了否定 → 事实翻转风险）。

    仅计数、跨语言不精确 → MAJOR（交人工），不自动 BLOCK。
    """
    s = _count_negations(source, source_lang)
    t = _count_negations(target, target_lang)
    if s == t:
        return None
    return LocalizationQAFinding(
        sentence_id=sentence_id,
        check=LocalizationQACheck.NEGATION_CONSISTENCY,
        severity=QASeverity.MAJOR,
        detail=f"否定标记数不一致：源 {s} 个 vs 译 {t} 个（可能否定翻转，须人工核）",
        evidence={"source_negations": s, "target_negations": t},
    )


@dataclass(frozen=True)
class ConsistencyPair:
    """一句的源/目标文本对（喂给一致性检查）。"""

    sentence_id: str
    source: str
    target: str
    source_lang: str
    target_lang: str


def run_consistency_checks(
    pairs: list[ConsistencyPair],
) -> list[LocalizationQAFinding]:
    """对每句跑纯一致性检查（数字 + 否定），汇总发现。"""
    findings: list[LocalizationQAFinding] = []
    for p in pairs:
        nf = check_number_consistency(p.sentence_id, p.source, p.target)
        if nf is not None:
            findings.append(nf)
        gf = check_negation_consistency(
            p.sentence_id, p.source, p.target,
            source_lang=p.source_lang, target_lang=p.target_lang,
        )
        if gf is not None:
            findings.append(gf)
    return findings


def validate_localization_publish_gate(
    findings: list[LocalizationQAFinding],
    *, max_major_before_block: int = DEFAULT_MAX_MAJOR_BEFORE_BLOCK,
) -> bool:
    """发布门：返回 pass_or_block（True=可发布）。

    任一 BLOCKER → 拦；MAJOR 数 > 阈值 → 拦；否则放行（MINOR/INFO 仅报告）。
    """
    if any(f.severity is QASeverity.BLOCKER for f in findings):
        return False
    majors = sum(1 for f in findings if f.severity is QASeverity.MAJOR)
    if majors > max_major_before_block:
        return False
    return True


def aggregate_localization_qa(
    findings: list[LocalizationQAFinding],
    *,
    id: str,
    localization_variant_id: str,
    reviewed_sentence_ids: list[str],
    created_at: datetime,
    max_major_before_block: int = DEFAULT_MAX_MAJOR_BEFORE_BLOCK,
) -> LocalizationQAReport:
    """把各层（一致性/字幕/TTS/口型…）逐句发现装配成 QA 报告，并算发布门。

    发现由调用方从各层护栏映射后传入（保持本函数纯装配 + 门计算）。
    """
    pass_or_block = validate_localization_publish_gate(
        findings, max_major_before_block=max_major_before_block,
    )
    return LocalizationQAReport(
        id=id,
        localization_variant_id=localization_variant_id,
        findings=list(findings),
        reviewed_sentence_ids=list(reviewed_sentence_ids),
        pass_or_block=pass_or_block,
        created_at=created_at,
    )


# §13 每种编辑类型触发的**逐句**下游阶段（不含全局 AUDIO_MIX/RENDER）
_EDIT_STAGE_CHAIN: dict[ReRunEditKind, tuple[ReRunStage, ...]] = {
    # 改译文 → 该句 TTS（text_hash 变）→ 字幕（跟 TTS forced-align）→ 口型（跟 dub 音频）
    ReRunEditKind.TEXT_EDIT: (ReRunStage.TTS, ReRunStage.SUBTITLE, ReRunStage.LIPSYNC),
    ReRunEditKind.VOICE_CHANGE: (ReRunStage.TTS, ReRunStage.SUBTITLE, ReRunStage.LIPSYNC),
    ReRunEditKind.TIMING_CHANGE: (ReRunStage.TTS, ReRunStage.SUBTITLE, ReRunStage.LIPSYNC),
}
# 全局下游：任一句变都要重混音 + 重渲染（一次）
_GLOBAL_STAGES: tuple[ReRunStage, ...] = (ReRunStage.AUDIO_MIX, ReRunStage.RENDER)


def compute_rerun_scope(
    edited_sentence_ids: list[str],
    all_sentence_ids: list[str],
    *,
    edit_kind: ReRunEditKind = ReRunEditKind.TEXT_EDIT,
) -> ReRunScope:
    """§13：改单句译文 → 只重跑该句 TTS/字幕/口型 + 下游渲染。

    不变量：`per_sentence_stages` 只含被编辑句；未编辑句进 `unaffected_sentence_ids`
    且**零阶段**；`TRANSLATION` 绝不出现在重跑集（改译文本身就是输入，不重跑翻译）。
    编辑集必须是 all_sentence_ids 的子集。
    """
    all_ids = list(dict.fromkeys(all_sentence_ids))  # 去重保序
    all_set = set(all_ids)
    edited = [s for s in dict.fromkeys(edited_sentence_ids) if s in all_set]
    unknown = [s for s in dict.fromkeys(edited_sentence_ids) if s not in all_set]
    if unknown:
        raise ValueError(f"编辑的句不在 all_sentence_ids 内：{unknown}")

    stages = _EDIT_STAGE_CHAIN[edit_kind]
    edited_set = set(edited)
    per_sentence = {sid: stages for sid in edited}
    unaffected = tuple(s for s in all_ids if s not in edited_set)
    return ReRunScope(
        edit_kind=edit_kind,
        edited_sentence_ids=tuple(edited),
        per_sentence_stages=per_sentence,
        global_stages=_GLOBAL_STAGES if edited else (),
        unaffected_sentence_ids=unaffected,
    )


def sentence_review_queue(report: LocalizationQAReport) -> list[str]:
    """需人工复核的句（有任何发现的句），按报告顺序去重。"""
    seen: set[str] = set()
    queue: list[str] = []
    for f in report.findings:
        if f.sentence_id not in seen:
            seen.add(f.sentence_id)
            queue.append(f.sentence_id)
    return queue


def validate_localization_review(
    review: LocalizationReview,
    findings: list[LocalizationQAFinding],
) -> list[LocalizationReviewIssue]:
    """句级批准护栏：不能批准仍带 BLOCKER 的句。"""
    issues: list[LocalizationReviewIssue] = []
    blocker_sentences = {
        f.sentence_id for f in findings if f.severity is QASeverity.BLOCKER
    }
    for d in review.decisions:
        if d.state is ReviewState.APPROVED and d.sentence_id in blocker_sentences:
            issues.append(LocalizationReviewIssue(
                LocalizationReviewIssueKind.APPROVED_OVER_BLOCKER, d.sentence_id,
                "不能批准仍带 BLOCKER 发现的句——须先修复或改译（EDITED）",
            ))
    return issues


def is_valid_localization_review(
    review: LocalizationReview, findings: list[LocalizationQAFinding],
) -> bool:
    return not validate_localization_review(review, findings)
