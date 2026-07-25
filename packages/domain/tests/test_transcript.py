"""转录低置信标记：纯、不改输入、可重放；段级或含低置信词即标记。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    Transcript,
    TranscriptModels,
    TranscriptSegment,
    TranscriptWord,
)
from videoforge_domain import low_confidence_spans, mark_low_confidence, needs_review

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _seg(sid, start, end, conf, words=()) -> TranscriptSegment:
    return TranscriptSegment(
        id=sid,
        start_ms=start,
        end_ms=end,
        language="zh-CN",
        text="…",
        confidence=conf,
        words=list(words),
    )


def _transcript(segments) -> Transcript:
    return Transcript(
        id="t1",
        language="zh-CN",
        segments=segments,
        models=TranscriptModels(asr_provider="asr.whisperx"),
        created_at=_T0,
    )


def test_marks_low_confidence_words_and_segments() -> None:
    t = _transcript(
        [
            _seg(
                "s0",
                0,
                1000,
                0.95,
                [
                    TranscriptWord(text="高", start_ms=0, end_ms=400, confidence=0.95),
                    TranscriptWord(text="低", start_ms=400, end_ms=1000, confidence=0.4),
                ],
            ),
            _seg("s1", 1000, 2000, 0.5),  # 段级置信度低
            _seg("s2", 2000, 3000, 0.9),  # 全高
        ]
    )
    out = mark_low_confidence(t)
    assert out.segments[0].words[0].low_confidence is False
    assert out.segments[0].words[1].low_confidence is True  # 低置信词
    assert out.segments[0].low_confidence is True  # 含低置信词 → 段也标
    assert out.segments[1].low_confidence is True  # 段级低
    assert out.segments[2].low_confidence is False  # 全高不标


def test_does_not_mutate_input() -> None:
    t = _transcript([_seg("s0", 0, 1000, 0.3)])
    assert t.segments[0].low_confidence is False
    mark_low_confidence(t)
    assert t.segments[0].low_confidence is False  # 输入未被改动


def test_replayable() -> None:
    t = _transcript([_seg("s0", 0, 1000, 0.5), _seg("s1", 1000, 2000, 0.9)])
    a, b = mark_low_confidence(t), mark_low_confidence(t)
    assert a == b


def test_needs_review_and_spans() -> None:
    t = mark_low_confidence(_transcript([_seg("s0", 100, 900, 0.4), _seg("s1", 900, 1800, 0.95)]))
    assert needs_review(t) is True
    assert low_confidence_spans(t) == [(100, 900)]  # 只低置信段


def test_all_high_confidence_needs_no_review() -> None:
    t = mark_low_confidence(_transcript([_seg("s0", 0, 1000, 0.99)]))
    assert needs_review(t) is False
    assert low_confidence_spans(t) == []


def test_threshold_is_configurable() -> None:
    t = _transcript([_seg("s0", 0, 1000, 0.65)])
    assert mark_low_confidence(t, segment_threshold=0.7).segments[0].low_confidence is True
    assert mark_low_confidence(t, segment_threshold=0.6).segments[0].low_confidence is False
