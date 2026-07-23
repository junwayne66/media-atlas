"""CreativeTimeline：§8.3 Validator 各 issue + OTIO 往返 semantic 保持。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    CreativeTimeline,
    LocalizationPolicy,
    RationalTime,
    RationalTimeRange,
    Segment,
    SegmentEffect,
    Track,
    TrackKind,
)
from videoforge_domain import (
    TimelineIssueKind,
    from_otio_mapping,
    is_valid_timeline,
    to_otio_mapping,
    validate_timeline,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _rt(v: int, rate: int = 30) -> RationalTime:
    return RationalTime(value=v, rate=rate)


def _rng(start: int, dur: int, rate: int = 30) -> RationalTimeRange:
    return RationalTimeRange(start=_rt(start, rate), duration=_rt(dur, rate))


def _seg(sid: str, start: int, dur: int, rate: int = 30, **kw) -> Segment:
    return Segment(id=sid, time_range=_rng(start, dur, rate), **kw)


def _track(kind: TrackKind, segs: list[Segment], *, tid: str | None = None) -> Track:
    return Track(id=tid or kind.value.lower(), kind=kind, segments=segs)


def _timeline(tracks: list[Track], *, duration: int = 150, rate: int = 30) -> CreativeTimeline:
    return CreativeTimeline(
        id="tl", rate=rate, duration=_rt(duration, rate), tracks=tracks, created_at=_T0,
    )


# —— Validator ——

def test_valid_minimal_timeline_passes() -> None:
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [_seg("v0", 0, 150)])
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 150)])
    assert validate_timeline(_timeline([v1, a0])) == []
    assert is_valid_timeline(_timeline([v1, a0]))


def test_empty_timeline_flagged() -> None:
    tl = _timeline([])
    kinds = {i.kind for i in validate_timeline(tl)}
    assert TimelineIssueKind.EMPTY_TIMELINE in kinds


def test_required_video_track_missing() -> None:
    # 只有音频轨、缺 V1
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 150)])
    tl = _timeline([a0])
    issues = validate_timeline(tl)
    kinds = {i.kind for i in issues}
    assert TimelineIssueKind.REQUIRED_TRACK_MISSING in kinds
    assert any("V1" in i.detail for i in issues)


def test_required_audio_track_missing() -> None:
    # 只有视频轨、缺 A0/A1
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [_seg("v0", 0, 150)])
    tl = _timeline([v1])
    issues = validate_timeline(tl)
    assert any(i.kind is TimelineIssueKind.REQUIRED_TRACK_MISSING and "A0" in i.detail
               for i in issues)


def test_a1_dub_also_satisfies_audio_requirement() -> None:
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [_seg("v0", 0, 150)])
    a1 = _track(TrackKind.A1_DUB, [_seg("a1", 0, 150)])
    assert validate_timeline(_timeline([v1, a1])) == []


def test_time_out_of_range_flagged() -> None:
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [_seg("v0", 100, 200)])  # 100+200=300 > 150
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 150)])
    kinds = {i.kind for i in validate_timeline(_timeline([v1, a0]))}
    assert TimelineIssueKind.TIME_OUT_OF_RANGE in kinds


def test_rate_mismatch_flagged() -> None:
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [_seg("v0", 0, 100, rate=25)])  # 25 ≠ 30
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 150)])
    kinds = {i.kind for i in validate_timeline(_timeline([v1, a0]))}
    assert TimelineIssueKind.RATE_MISMATCH in kinds


def test_segment_overlap_within_track_flagged() -> None:
    v1 = _track(
        TrackKind.V1_PRIMARY_VIDEO,
        [_seg("v0", 0, 100), _seg("v1", 50, 50)],  # v1 起点 50 < v0 结束 100
    )
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 150)])
    kinds = {i.kind for i in validate_timeline(_timeline([v1, a0]))}
    assert TimelineIssueKind.SEGMENT_OVERLAP in kinds


def test_adjacent_segments_not_overlap() -> None:
    # 相接（a.end == b.start）不判重叠
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [_seg("v0", 0, 60), _seg("v1", 60, 90)])
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 150)])
    assert validate_timeline(_timeline([v1, a0])) == []


def test_invalid_provenance_ref_flagged() -> None:
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [_seg("v0", 0, 150, provenance_ref="  ")])
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 150)])
    kinds = {i.kind for i in validate_timeline(_timeline([v1, a0]))}
    assert TimelineIssueKind.INVALID_PROVENANCE_REF in kinds


# —— OTIO 往返 ——

def test_to_otio_mapping_structure() -> None:
    v1 = _track(
        TrackKind.V1_PRIMARY_VIDEO,
        [_seg("v0", 0, 150, source_ref="asset-a", semantic_role="HOOK",
              script_sentence_id="s-0")],
    )
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 150)])
    otio = to_otio_mapping(_timeline([v1, a0]))
    assert otio["OTIO_SCHEMA"] == "Timeline.1"
    tracks = otio["tracks"]["children"]
    assert [t["name"] for t in tracks] == ["v1_primary_video", "a0_original"]
    assert tracks[0]["kind"] == "Video" and tracks[1]["kind"] == "Audio"
    # 扩展字段落 metadata.videoforge
    clip = tracks[0]["children"][0]
    vf = clip["metadata"]["videoforge"]
    assert vf["source_ref"] == "asset-a"
    assert vf["semantic_role"] == "HOOK"
    assert vf["script_sentence_id"] == "s-0"


def test_otio_roundtrip_preserves_padded_duration() -> None:
    # 回归：源 timeline 末段留白（duration > 段最远 end）时，往返仍保原 duration；
    # metadata.videoforge.duration_value 显式携带 —— 消除 max(end) 简化带来的信息损失。
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [_seg("v0", 0, 100)])  # 到 100
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 100)])
    original = _timeline([v1, a0], duration=150)  # 末段 50 帧留白
    restored = from_otio_mapping(to_otio_mapping(original), created_at=_T0)
    assert restored.duration.value == 150 and restored.duration.rate == 30


def test_from_otio_falls_back_to_max_end_when_duration_absent() -> None:
    # 兼容外部产出的 OTIO dict：缺 metadata.videoforge.duration_value 时用 max(end) 兜底
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [_seg("v0", 0, 100)])
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 100)])
    dumped = to_otio_mapping(_timeline([v1, a0], duration=150))
    del dumped["metadata"]["videoforge"]["duration_value"]  # 模拟外部产出
    restored = from_otio_mapping(dumped, created_at=_T0)
    assert restored.duration.value == 100  # 退化为 max(end)


def test_otio_roundtrip_preserves_extension_fields() -> None:
    v1 = _track(TrackKind.V1_PRIMARY_VIDEO, [
        _seg("v0", 0, 150, source_ref="asset-a", semantic_role="EVIDENCE",
             script_sentence_id="s-1", speaker_id="host",
             provenance_ref="ra-1", template_slot="slot-3",
             effects=[SegmentEffect(kind="fade_in", params={"duration_ms": 300})],
             crop_path="crop-a",
             localization=LocalizationPolicy(language="zh-CN", strategy="dub")),
    ])
    a0 = _track(TrackKind.A0_ORIGINAL, [_seg("a0", 0, 150)])
    original = _timeline([v1, a0])
    dumped = to_otio_mapping(original)
    restored = from_otio_mapping(dumped, created_at=_T0)
    # 结构 semantic 一致：轨道数、类型、每 segment 扩展字段全部还原
    assert restored.rate == original.rate
    assert restored.duration == original.duration
    assert [(t.kind, [s.id for s in t.segments]) for t in restored.tracks] == \
           [(t.kind, [s.id for s in t.segments]) for t in original.tracks]
    r_seg = restored.tracks[0].segments[0]
    assert r_seg.source_ref == "asset-a"
    assert r_seg.semantic_role == "EVIDENCE"
    assert r_seg.script_sentence_id == "s-1"
    assert r_seg.provenance_ref == "ra-1"
    assert r_seg.effects[0].kind == "fade_in"
    assert r_seg.effects[0].params["duration_ms"] == 300
    assert r_seg.localization is not None
    assert r_seg.localization.language == "zh-CN"
    assert r_seg.crop_path == "crop-a"
    # 往返后仍过 Validator
    assert validate_timeline(restored) == []
