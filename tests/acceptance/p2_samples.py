"""P2 Exit 试点样本集（docs/implementation/54 §1、53 §P2 Exit）。

≥20 条中性合成样本（NOT 真实媒体）：中/英/混语，含低置信、说话人切换、文本轨、视觉帧、
不同时长。每条 = transcript + text_tracks + visual_analysis + duration，供 P2 全链路
（ASR→OCR→VLM→Blueprint 融合）走通并验证 Blueprint 可追溯到证据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from videoforge_contracts import (
    BBox,
    FrameAnalysis,
    FrameSampleReason,
    TextObservation,
    TextTrack,
    TextTrackKind,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
    VisualAnalysis,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


@dataclass(frozen=True)
class Sample:
    id: str
    language: str
    duration_ms: int
    transcript: Transcript
    text_tracks: tuple[TextTrack, ...] = ()
    visual_analysis: VisualAnalysis = field(
        default_factory=lambda: VisualAnalysis(
            id="va", sampling_policy="representative@v1", frames=[], created_at=_T0
        )
    )


def _seg(sid, start, end, speaker, lang, text, low=False) -> TranscriptSegment:
    return TranscriptSegment(
        id=sid, start_ms=start, end_ms=end, speaker_id=speaker, language=lang,
        text=text, confidence=0.45 if low else 0.9, low_confidence=low,
    )


def _track(tid, start, end, text, low=False) -> TextTrack:
    return TextTrack(
        id=tid, kind=TextTrackKind.CAPTION, text=text, start_ms=start, end_ms=end,
        confidence=0.4 if low else 0.9, low_confidence=low,
        observations=[TextObservation(
            frame_time_ms=start, bbox=BBox(x=0.2, y=0.82, w=0.6, h=0.08), text=text, confidence=0.9
        )],
    )


def _va(frames: list[tuple[int, list[str]]]) -> VisualAnalysis:
    return VisualAnalysis(
        id="va", sampling_policy="representative@v1",
        frames=[
            FrameAnalysis(frame_time_ms=t, reasons=[FrameSampleReason.KEYFRAME], labels=labels)
            for t, labels in frames
        ],
        created_at=_T0,
    )


def _transcript(segments: list[TranscriptSegment], lang: str) -> Transcript:
    return Transcript(
        id="tr", language=lang, segments=segments,
        models=TranscriptModels(asr_provider="asr.fake", asr_model="fixture"), created_at=_T0,
    )


def p2_samples() -> list[Sample]:
    samples: list[Sample] = []

    # —— 中文 8 条（含低置信、说话人切换、水印/字幕轨、视觉帧）——
    for i in range(8):
        dur = 12000 + i * 4000
        segs = [
            _seg("seg-0", 0, 3000, "spk_0", "zh-CN", f"大家好这是第{i}个演示"),
            _seg("seg-1", 4000, 8000, "spk_0", "zh-CN", "重点看这个功能", low=(i % 3 == 0)),
            _seg("seg-2", 9000, min(dur, 12000), "spk_1" if i % 2 else "spk_0", "zh-CN", "小结"),
        ]
        samples.append(Sample(
            id=f"zh-{i}", language="zh-CN", duration_ms=dur,
            transcript=_transcript(segs, "zh-CN"),
            text_tracks=(_track("tt-0", 1000, 3500, "第一屏字幕", low=(i % 4 == 0)),),
            visual_analysis=_va([(0, ["person"]), (4000, ["screen_record"]), (9000, ["product"])]),
        ))

    # —— 英文 8 条 ——
    for i in range(8):
        dur = 10000 + i * 3000
        segs = [
            _seg("seg-0", 0, 2500, "spk_0", "en-US", f"welcome to demo {i}"),
            _seg("seg-1", 3000, 7000, "spk_1" if i % 2 else "spk_0", "en-US", "the key part",
                 low=(i % 5 == 0)),
        ]
        samples.append(Sample(
            id=f"en-{i}", language="en-US", duration_ms=dur,
            transcript=_transcript(segs, "en-US"),
            text_tracks=(_track("tt-0", 500, 2500, "opening caption"),),
            visual_analysis=_va([(0, ["person"]), (3000, ["chart"])]),
        ))

    # —— 混语 6 条（段内不同 language）——
    for i in range(6):
        dur = 14000
        segs = [
            _seg("seg-0", 0, 3000, "spk_0", "zh-CN", "今天聊聊 AI 工具"),
            _seg("seg-1", 3500, 7000, "spk_0", "en-US", "the on device model is fast",
                 low=(i % 2 == 0)),
            _seg("seg-2", 8000, 13000, "spk_1", "zh-CN", "回到中文继续讲"),
        ]
        samples.append(Sample(
            id=f"mix-{i}", language="zh-CN", duration_ms=dur,
            transcript=_transcript(segs, "zh-CN"),
            text_tracks=(
                _track("tt-0", 500, 3000, "中文字幕"),
                _track("tt-1", 3500, 7000, "english caption", low=(i % 3 == 0)),
            ),
            visual_analysis=_va([(0, ["person"]), (3500, ["screen_record"]), (8000, ["person"])]),
        ))

    return samples
