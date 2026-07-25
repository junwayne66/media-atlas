"""Blueprint 候选/视觉beat/校验护栏：铺满时间线、标签映射、越界/非单调/伪造引用/低覆盖都能查。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    Claim,
    EvidenceSpan,
    FrameAnalysis,
    FrameSampleReason,
    RhetoricalBeat,
    RhetoricalBeatKind,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
    VideoBlueprint,
    VisualAnalysis,
    VisualBeatKind,
)
from videoforge_domain import (
    BlueprintIssueKind,
    build_candidate_rhetorical_beats,
    build_visual_beats,
    coverage_ratio,
    is_valid_blueprint,
    validate_blueprint,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _transcript(*spans) -> Transcript:
    return Transcript(
        id="tr",
        language="zh-CN",
        segments=[
            TranscriptSegment(
                id=f"seg-{i}",
                start_ms=s,
                end_ms=e,
                speaker_id="spk_0",
                language="zh-CN",
                text=f"句{i}",
                confidence=0.9,
            )
            for i, (s, e) in enumerate(spans)
        ],
        models=TranscriptModels(asr_provider="asr.x"),
        created_at=_T0,
    )


def _va(*frames) -> VisualAnalysis:
    return VisualAnalysis(
        id="va",
        sampling_policy="representative@v1",
        frames=[
            FrameAnalysis(frame_time_ms=t, reasons=[FrameSampleReason.KEYFRAME], labels=labels)
            for t, labels in frames
        ],
        created_at=_T0,
    )


def _bp(**over) -> VideoBlueprint:
    kwargs = dict(id="bp", duration_ms=10000, created_at=_T0)
    kwargs.update(over)
    return VideoBlueprint(**kwargs)


def _kinds(bp, *, segs=frozenset(), tracks=frozenset()) -> set:
    issues = validate_blueprint(bp, transcript_segment_ids=set(segs), text_track_ids=set(tracks))
    return {i.kind for i in issues}


# —— 候选 / 视觉 beat ——


def test_candidates_tile_the_timeline() -> None:
    beats = build_candidate_rhetorical_beats(_transcript((0, 3000), (5000, 8000)), 10000)
    # 铺满 [0,10000]：语音段 + 间隙 + 尾部，全 UNCLASSIFIED
    assert beats[0].start_ms == 0 and beats[-1].end_ms == 10000
    assert all(b.kind is RhetoricalBeatKind.UNCLASSIFIED for b in beats)
    # 连续无缝（成对滑窗，天然差 1）
    for a, b in zip(beats, beats[1:], strict=False):
        assert a.end_ms == b.start_ms


def test_candidates_no_transcript_is_single_span() -> None:
    beats = build_candidate_rhetorical_beats(None, 10000)
    assert len(beats) == 1 and beats[0].start_ms == 0 and beats[0].end_ms == 10000


def test_visual_beats_map_labels() -> None:
    beats = build_visual_beats(_va((0, ["person"]), (3000, ["screen_record", "chart"])), 10000)
    assert beats[0].kind is VisualBeatKind.PERSON
    assert beats[1].kind is VisualBeatKind.SCREEN_RECORD  # screen 优先于 chart
    assert beats[0].end_ms == 3000 and beats[1].end_ms == 10000  # 跨到下帧/时长


def test_candidates_clamp_out_of_range_segments() -> None:
    # 上游段起点超出目标时长 → 候选全部落在 [0,duration] 内（不产出越界候选）
    beats = build_candidate_rhetorical_beats(_transcript((0, 2000), (10100, 10200)), 10000)
    assert all(0 <= b.start_ms <= b.end_ms <= 10000 for b in beats)
    assert beats[-1].end_ms == 10000


def test_visual_beats_skip_out_of_range_frame() -> None:
    # frame_time_ms 超出目标时长 → 跳过，不崩溃、不产出非法 beat
    beats = build_visual_beats(_va((0, ["person"]), (10500, ["product"])), 10000)
    assert len(beats) == 1
    assert all(b.start_ms <= b.end_ms <= 10000 for b in beats)


# —— 校验护栏 ——


def _valid_bp() -> VideoBlueprint:
    return _bp(
        claims=[
            Claim(
                id="c0",
                text="x",
                evidence=[EvidenceSpan(kind="transcript", ref_id="seg-0", start_ms=0, end_ms=3000)],
            )
        ],
        rhetorical_beats=[
            RhetoricalBeat(
                id="r0", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=5000, claim_ids=["c0"]
            ),
            RhetoricalBeat(id="r1", kind=RhetoricalBeatKind.CTA, start_ms=5000, end_ms=10000),
        ],
    )


def test_valid_blueprint_passes() -> None:
    segs = {"seg-0"}
    assert validate_blueprint(_valid_bp(), transcript_segment_ids=segs, text_track_ids=set()) == []
    assert is_valid_blueprint(_valid_bp(), transcript_segment_ids=segs, text_track_ids=set())
    assert coverage_ratio(_valid_bp()) == 1.0


def test_time_out_of_range_detected() -> None:
    bp = _bp(
        rhetorical_beats=[
            RhetoricalBeat(id="r0", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=99999)
        ]
    )
    kinds = _kinds(bp)
    assert BlueprintIssueKind.TIME_OUT_OF_RANGE in kinds


def test_non_monotonic_detected() -> None:
    bp = _bp(
        rhetorical_beats=[
            RhetoricalBeat(id="r0", kind=RhetoricalBeatKind.HOOK, start_ms=5000, end_ms=9000),
            RhetoricalBeat(id="r1", kind=RhetoricalBeatKind.CTA, start_ms=0, end_ms=4000),
        ]
    )
    kinds = _kinds(bp)
    assert BlueprintIssueKind.TIME_NOT_MONOTONIC in kinds


def test_invalid_evidence_ref_detected() -> None:
    bp = _bp(
        rhetorical_beats=[
            RhetoricalBeat(id="r0", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=10000)
        ],
        claims=[
            Claim(
                id="c0",
                text="x",
                evidence=[EvidenceSpan(kind="transcript", ref_id="NOPE", start_ms=0, end_ms=100)],
            )
        ],
    )
    kinds = _kinds(bp, segs={"seg-0"})
    assert BlueprintIssueKind.EVIDENCE_REF_INVALID in kinds


def test_beat_claim_ref_invalid_detected() -> None:
    bp = _bp(
        rhetorical_beats=[
            RhetoricalBeat(
                id="r0", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=10000, claim_ids=["ghost"]
            )
        ]
    )
    kinds = _kinds(bp)
    assert BlueprintIssueKind.BEAT_CLAIM_REF_INVALID in kinds


def test_low_coverage_detected() -> None:
    # 只覆盖 3000/10000 = 0.3 < 0.9
    bp = _bp(
        rhetorical_beats=[
            RhetoricalBeat(id="r0", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=3000)
        ]
    )
    kinds = _kinds(bp)
    assert BlueprintIssueKind.LOW_COVERAGE in kinds


def test_overlapping_beats_coverage_union() -> None:
    # 重叠区间按并集算覆盖，不重复计数
    bp = _bp(
        rhetorical_beats=[
            RhetoricalBeat(id="r0", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=6000),
            RhetoricalBeat(id="r1", kind=RhetoricalBeatKind.EVIDENCE, start_ms=4000, end_ms=10000),
        ]
    )
    assert coverage_ratio(bp) == 1.0  # 并集 0-10000
