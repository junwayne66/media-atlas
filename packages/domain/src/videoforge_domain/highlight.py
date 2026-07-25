"""热门片段识别（docs/modules/42 §5）。纯函数，可复现。

- build_candidate_windows：在转录句子边界生成 [min,max] 时长窗口，**绝不切句**（端点永远落在
  句子边界）——§5.1 的"强制避免句中截断"由构造保证。
- highlight_score：§5.2 加权公式，系数读 HighlightWeights 模板，惩罚项负号在公式里，bit 级可复现。
- rank_highlights：重叠 >阈值去重（留高分）+ MMR 平衡分数与多样性 → Top-N HighlightCandidate。

MMR 的相似度 = max(时间重叠, 特征向量余弦)。特征余弦是"主题/人物/视觉多样性"的近似代理——真正的
主题/人物身份需要向量嵌入（校准项，延后）；predicted_retention 同理，无训练数据时保持 null 不伪装。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from videoforge_contracts import (
    HighlightCandidate,
    HighlightFeatures,
    HighlightReason,
    HighlightSet,
    HighlightWeights,
    Transcript,
)

# 窗口时长区间（ms）——短视频重剪 5–30s、长访谈 20–90s，默认取通用 12–75s（§5.1）
_DEFAULT_MIN_MS = 12_000
_DEFAULT_MAX_MS = 75_000
_REASON_THRESHOLD = 0.6  # 特征子分 ≥ 此值即派生对应理由码
_OVERLAP_THRESHOLD = 0.7  # 重叠 > 此值判重复，只留高分（§5.3）
_MMR_LAMBDA = 0.7  # MMR：分数 vs 多样性的权衡（越大越偏分数）

# highlight_score 中所有项对应的特征名（正向 9 + 惩罚 2），也用于特征向量相似度
_FEATURE_KEYS = (
    "hook_strength",
    "self_containedness",
    "information_density",
    "surprise_or_conflict",
    "emotional_energy",
    "topic_relevance",
    "visual_activity",
    "speaker_prominence",
    "ending_payoff",
    "context_dependency",
    "technical_defect",
)


@dataclass(frozen=True)
class CandidateWindow:
    """域内候选窗口（未评分）：句子边界对齐，不切句。"""

    start_ms: int
    end_ms: int
    segment_ids: tuple[str, ...]
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def build_candidate_windows(
    transcript: Transcript,
    *,
    min_ms: int = _DEFAULT_MIN_MS,
    max_ms: int = _DEFAULT_MAX_MS,
) -> list[CandidateWindow]:
    """按转录句子边界生成 [min_ms, max_ms] 内的候选窗口，绝不切句（§5.1）。

    每个起始句 i 向后贪心累积连续句 j，窗口结束取"已纳入所有句子的最远 end"（cover_end），故窗口
    完整包住每一个纳入句、绝不截断——即使 diarize 串话使片段重叠（后一句 end 反而更小）也成立。
    对非重叠转录 cover_end == segs[j].end，行为与朴素累积一致；端点永远落在某句边界，不断呼吸。
    单句超过 max_ms 者不产窗口（不能不切句地放入）。cover_end 随 j 单调不减，超上限即可 break。
    """
    if min_ms > max_ms:
        raise ValueError(f"min_ms({min_ms}) > max_ms({max_ms})")
    segs = sorted(transcript.segments, key=lambda s: (s.start_ms, s.end_ms))
    windows: list[CandidateWindow] = []
    for i in range(len(segs)):
        cover_end = segs[i].end_ms
        for j in range(i, len(segs)):
            cover_end = max(cover_end, segs[j].end_ms)  # 覆盖到已纳入句子的最远结束，绝不截断
            dur = cover_end - segs[i].start_ms
            if dur > max_ms:
                break  # cover_end 单调不减，继续加句只会更长
            if dur >= min_ms:
                windows.append(
                    CandidateWindow(
                        start_ms=segs[i].start_ms,
                        end_ms=cover_end,
                        segment_ids=tuple(s.id for s in segs[i : j + 1]),
                        text=" ".join(s.text for s in segs[i : j + 1]),
                    )
                )
    return windows


def highlight_score(features: HighlightFeatures, weights: HighlightWeights) -> float:
    """§5.2 加权公式。惩罚项（context_dependency/technical_defect）在此取负，权重本身为量级。"""
    return (
        weights.hook_strength * features.hook_strength
        + weights.self_containedness * features.self_containedness
        + weights.information_density * features.information_density
        + weights.surprise_or_conflict * features.surprise_or_conflict
        + weights.emotional_energy * features.emotional_energy
        + weights.topic_relevance * features.topic_relevance
        + weights.visual_activity * features.visual_activity
        + weights.speaker_prominence * features.speaker_prominence
        + weights.ending_payoff * features.ending_payoff
        - weights.context_dependency * features.context_dependency
        - weights.technical_defect * features.technical_defect
    )


def derive_highlight_reasons(
    features: HighlightFeatures, *, threshold: float = _REASON_THRESHOLD
) -> list[HighlightReason]:
    """特征子分 ≥ 阈值 → 对应理由码。固定顺序，确定性（§5.3）。"""
    reasons: list[HighlightReason] = []
    if features.hook_strength >= threshold:
        reasons.append(HighlightReason.HOOK_QUOTE)
    if features.ending_payoff >= threshold:
        reasons.append(HighlightReason.CLEAR_PAYOFF)
    if features.information_density >= threshold:
        reasons.append(HighlightReason.HIGH_INFO_DENSITY)
    if features.surprise_or_conflict >= threshold:
        reasons.append(HighlightReason.SURPRISE)
    if features.emotional_energy >= threshold:
        reasons.append(HighlightReason.EMOTIONAL_PEAK)
    if features.self_containedness >= threshold:
        reasons.append(HighlightReason.SELF_CONTAINED)
    if features.topic_relevance >= threshold:
        reasons.append(HighlightReason.STRONG_TOPIC)
    if features.visual_activity >= threshold:
        reasons.append(HighlightReason.VISUAL_ACTION)
    # 谨慎项：偏高即标注，供人工注意（不阻断，仅提示）
    if features.context_dependency >= threshold:
        reasons.append(HighlightReason.CONTEXT_DEPENDENT)
    if features.technical_defect >= threshold:
        reasons.append(HighlightReason.TECHNICAL_DEFECT)
    return reasons


def overlap_ratio(a: CandidateWindow, b: CandidateWindow) -> float:
    """时间重叠 / 较短窗时长。较小窗完全落入较大窗 → 1.0（§5.3 去重用）。"""
    inter = max(0, min(a.end_ms, b.end_ms) - max(a.start_ms, b.start_ms))
    shorter = min(a.duration_ms, b.duration_ms)
    if shorter <= 0:
        return 0.0
    return inter / shorter


def _feature_vector(f: HighlightFeatures) -> tuple[float, ...]:
    return tuple(getattr(f, k) for k in _FEATURE_KEYS)


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class _Scored:
    window: CandidateWindow
    features: HighlightFeatures
    score: float
    reasons: list[HighlightReason] = field(default_factory=list)


def _similarity(a: _Scored, b: _Scored) -> float:
    """MMR 多样性用相似度：时间重叠 与 特征向量余弦 取大者（后者是主题/视觉多样性的近似代理）。"""
    return max(
        overlap_ratio(a.window, b.window),
        _cosine(_feature_vector(a.features), _feature_vector(b.features)),
    )


def rank_highlights(
    windows: list[CandidateWindow],
    features: list[HighlightFeatures],
    *,
    weights: HighlightWeights,
    top_n: int,
    id_prefix: str,
    created_at: datetime,
    source_transcript_id: str | None = None,
    feature_provider: str | None = None,
    overlap_threshold: float = _OVERLAP_THRESHOLD,
    mmr_lambda: float = _MMR_LAMBDA,
    reason_threshold: float = _REASON_THRESHOLD,
) -> HighlightSet:
    """窗口 + 特征 → 打分 → 重叠去重 → MMR 多样性 → Top-N HighlightSet（确定性，可复现）。"""
    if len(windows) != len(features):
        raise ValueError(f"windows({len(windows)}) 与 features({len(features)}) 数量不一致")

    scored = [
        _Scored(
            w,
            f,
            highlight_score(f, weights),
            derive_highlight_reasons(f, threshold=reason_threshold),
        )
        for w, f in zip(windows, features, strict=True)
    ]
    # 确定性排序：分数降序，其次起点/时长/片段 id（平票时 MMR 与去重取此序首个）
    scored.sort(
        key=lambda s: (-s.score, s.window.start_ms, s.window.duration_ms, s.window.segment_ids)
    )

    # 去重：按分数序贪心接受，与已接受窗重叠 > 阈值者丢弃（§5.3）
    survivors: list[_Scored] = []
    for cand in scored:
        if any(overlap_ratio(cand.window, kept.window) > overlap_threshold for kept in survivors):
            continue
        survivors.append(cand)

    # MMR：分数（min-max 归一到 [0,1]）与"与已选最大相似度"权衡，逐个选出 Top-N
    lo = min((s.score for s in survivors), default=0.0)
    hi = max((s.score for s in survivors), default=0.0)

    def norm(s: float) -> float:
        return (s - lo) / (hi - lo) if hi > lo else 1.0

    selected: list[_Scored] = []
    pool = list(survivors)
    while pool and len(selected) < top_n:
        best: _Scored | None = None
        best_val = -math.inf
        for cand in pool:
            if not selected:
                val = norm(cand.score)
            else:
                max_sim = max(_similarity(cand, chosen) for chosen in selected)
                val = mmr_lambda * norm(cand.score) - (1 - mmr_lambda) * max_sim
            if val > best_val:  # pool 已确定性排序，平票取首个
                best_val = val
                best = cand
        assert best is not None
        selected.append(best)
        pool.remove(best)

    candidates = [
        HighlightCandidate(
            id=f"{id_prefix}-{rank}",
            source_transcript_id=source_transcript_id,
            start_ms=s.window.start_ms,
            end_ms=s.window.end_ms,
            segment_ids=list(s.window.segment_ids),
            score=s.score,
            features=s.features,
            reason_codes=s.reasons,
            weights_version=weights.template_version,
        )
        for rank, s in enumerate(selected)
    ]
    return HighlightSet(
        id=id_prefix,
        source_transcript_id=source_transcript_id,
        candidates=candidates,
        weights_version=weights.template_version,
        feature_provider=feature_provider,
        created_at=created_at,
    )
