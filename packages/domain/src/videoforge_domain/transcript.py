"""转录后处理：低置信审核标记（docs/modules/41 §7.2「低置信词进入审核标记」）。

纯函数：不改输入，返回带标记的新 Transcript，可重放。段被标为低置信当且仅当其段级
置信度低于阈值，或含任一低置信词——审核时优先看这些段/词。
"""

from __future__ import annotations

from videoforge_contracts import Transcript

_WORD_THRESHOLD = 0.6
_SEGMENT_THRESHOLD = 0.7


def mark_low_confidence(
    transcript: Transcript,
    *,
    word_threshold: float = _WORD_THRESHOLD,
    segment_threshold: float = _SEGMENT_THRESHOLD,
) -> Transcript:
    """返回新 Transcript：低于阈值的词/段打上 low_confidence。不改输入。"""
    new_segments = []
    for seg in transcript.segments:
        new_words = [
            w.model_copy(update={"low_confidence": w.confidence < word_threshold})
            for w in seg.words
        ]
        seg_low = seg.confidence < segment_threshold or any(w.low_confidence for w in new_words)
        new_segments.append(seg.model_copy(update={"words": new_words, "low_confidence": seg_low}))
    return transcript.model_copy(update={"segments": new_segments})


def needs_review(transcript: Transcript) -> bool:
    """转录是否需要人工审核（存在任一低置信段）。"""
    return any(seg.low_confidence for seg in transcript.segments)


def low_confidence_spans(transcript: Transcript) -> list[tuple[int, int]]:
    """所有低置信段的时间区间（ms），供审核 UI 跳转。"""
    return [(seg.start_ms, seg.end_ms) for seg in transcript.segments if seg.low_confidence]
