"""CreativeTimeline 校验 + OTIO 交换映射（docs/modules/42 §8，ADR-003）。纯函数，可复现。

- validate_timeline：§8.3 护栏——rate 一致（全 timeline 单一时基）、segment 时间范围在
  [0,duration] 内、同轨内不重叠（相接允许，a.end==b.start）、必填槽位（V1 主视频或 A0/A1 音频
  至少存一）、跨引用完整（provenance_ref 若给则不能空串）。
- to_otio_mapping/from_otio_mapping：纯 dict 映射，不依赖 opentimelineio 运行时；轨道名按 §8.1
  一一对应，扩展字段（source_ref/semantic_role/…/localization）落 clip.metadata.videoforge，
  往返 semantic 保持不变。ADR-003 binding：OTIO 是交换格式，CreativeTimeline 是**领域真值**。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from videoforge_contracts import (
    CreativeTimeline,
    RationalTime,
    RationalTimeRange,
    Segment,
    Track,
    TrackKind,
)

# 必填轨道（§8.3）：V1 主视频或 A0/A1 音频至少存一 —— 视频必存，音频至少一条
_REQUIRED_VIDEO = frozenset({TrackKind.V1_PRIMARY_VIDEO})
_REQUIRED_AUDIO_ANY = frozenset({TrackKind.A0_ORIGINAL, TrackKind.A1_DUB})


class TimelineIssueKind(StrEnum):
    RATE_MISMATCH = "RATE_MISMATCH"  # segment/track 与 timeline.rate 不一致
    TIME_OUT_OF_RANGE = "TIME_OUT_OF_RANGE"  # segment 超出 timeline.duration
    SEGMENT_OVERLAP = "SEGMENT_OVERLAP"  # 同轨内 segment 重叠
    REQUIRED_TRACK_MISSING = "REQUIRED_TRACK_MISSING"  # V1 或音频轨缺失
    EMPTY_TIMELINE = "EMPTY_TIMELINE"  # 无 track / 无 segment
    INVALID_PROVENANCE_REF = "INVALID_PROVENANCE_REF"  # 空串 provenance_ref


@dataclass(frozen=True)
class TimelineIssue:
    kind: TimelineIssueKind
    ref: str
    detail: str


def _seg_end_value(seg: Segment) -> int:
    return seg.time_range.start.value + seg.time_range.duration.value


def _rt_le(a: RationalTime, b: RationalTime) -> bool:
    # 同 rate 时直接比 value；不同 rate 时按 value/rate 秒比较（避免浮点，交叉相乘）
    return a.value * b.rate <= b.value * a.rate


def validate_timeline(timeline: CreativeTimeline) -> list[TimelineIssue]:
    """§8.3 护栏；返回全部违规（空 = 通过）。ADR-003：timeline 是领域真值，决定能否编译渲染。"""
    issues: list[TimelineIssue] = []
    rate = timeline.rate
    duration = timeline.duration

    if not timeline.tracks or all(not t.segments for t in timeline.tracks):
        issues.append(
            TimelineIssue(TimelineIssueKind.EMPTY_TIMELINE, timeline.id, "无轨或无 segment")
        )
        return issues

    track_kinds = {t.kind for t in timeline.tracks if t.segments}
    if not (_REQUIRED_VIDEO & track_kinds):
        issues.append(
            TimelineIssue(TimelineIssueKind.REQUIRED_TRACK_MISSING, timeline.id, "缺 V1 主视频轨")
        )
    if not (_REQUIRED_AUDIO_ANY & track_kinds):
        issues.append(
            TimelineIssue(
                TimelineIssueKind.REQUIRED_TRACK_MISSING, timeline.id, "缺 A0/A1 音频轨（至少存一）"
            )
        )

    for track in timeline.tracks:
        for seg in track.segments:
            if seg.time_range.start.rate != rate or seg.time_range.duration.rate != rate:
                issues.append(
                    TimelineIssue(
                        TimelineIssueKind.RATE_MISMATCH, seg.id,
                        f"segment 时基 ({seg.time_range.start.rate},"
                        f"{seg.time_range.duration.rate}) 与 timeline.rate={rate} 不一致",
                    )
                )
                continue  # rate 不齐时不再判越界，避免误报；is_valid 判定不受影响
            end = RationalTime(value=_seg_end_value(seg), rate=rate)
            if not _rt_le(end, duration) or seg.time_range.start.value < 0:
                issues.append(
                    TimelineIssue(
                        TimelineIssueKind.TIME_OUT_OF_RANGE, seg.id,
                        f"[{seg.time_range.start.value},{end.value}] 超出 [0,{duration.value}]",
                    )
                )
            if seg.provenance_ref is not None and not seg.provenance_ref.strip():
                issues.append(
                    TimelineIssue(
                        TimelineIssueKind.INVALID_PROVENANCE_REF, seg.id, "空 provenance_ref"
                    )
                )

        # 同轨重叠：按 start 排序，若下一个 start < 前一个 end 即重叠（相接 a.end==b.start 允许）。
        # 仅检查相邻对：由 sort 不变式可证"若无相邻对重叠则无对重叠"，故 is_valid 判定完整；
        # issue 列表在多重重叠时可能少列，此为可接受简化——首个报出的重叠已足够定位问题。
        sorted_segs = sorted(
            track.segments, key=lambda s: (s.time_range.start.value, _seg_end_value(s))
        )
        for a, b in zip(sorted_segs, sorted_segs[1:], strict=False):
            if b.time_range.start.value < _seg_end_value(a):
                issues.append(
                    TimelineIssue(
                        TimelineIssueKind.SEGMENT_OVERLAP, b.id,
                        f"与 {a.id} 在轨 {track.id} ({track.kind.value}) 重叠",
                    )
                )
    return issues


def is_valid_timeline(timeline: CreativeTimeline) -> bool:
    return not validate_timeline(timeline)


# —— OTIO 交换映射（纯 dict，不依赖 opentimelineio 运行时） ——


_TRACK_KIND_TO_OTIO_KIND: dict[TrackKind, str] = {
    TrackKind.V0_BACKGROUND: "Video",
    TrackKind.V1_PRIMARY_VIDEO: "Video",
    TrackKind.V2_BROLL_SCREEN: "Video",
    TrackKind.V3_INFO_CARDS: "Video",
    TrackKind.V4_CAPTIONS: "Video",
    TrackKind.V5_OVERLAYS: "Video",
    TrackKind.A0_ORIGINAL: "Audio",
    TrackKind.A1_DUB: "Audio",
    TrackKind.A2_MUSIC: "Audio",
    TrackKind.A3_SFX: "Audio",
    TrackKind.M0_MARKERS: "Video",  # OTIO 无原生标记轨；用 Video 承载 metadata
}

# metadata.videoforge 承载扩展字段的 key 集合（往返稳定）
_SEGMENT_EXTRA_KEYS = (
    "source_ref",
    "semantic_role",
    "script_sentence_id",
    "speaker_id",
    "provenance_ref",
    "template_slot",
    "crop_path",
)


def _rt_to_otio(rt: RationalTime) -> dict[str, Any]:
    return {"OTIO_SCHEMA": "RationalTime.1", "value": rt.value, "rate": rt.rate}


def _range_to_otio(r: RationalTimeRange) -> dict[str, Any]:
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "start_time": _rt_to_otio(r.start),
        "duration": _rt_to_otio(r.duration),
    }


def _segment_to_otio_clip(seg: Segment) -> dict[str, Any]:
    extras: dict[str, Any] = {
        k: getattr(seg, k) for k in _SEGMENT_EXTRA_KEYS if getattr(seg, k) is not None
    }
    if seg.effects:
        extras["effects"] = [{"kind": e.kind, "params": dict(e.params)} for e in seg.effects]
    if seg.localization is not None:
        extras["localization"] = {
            "language": seg.localization.language, "strategy": seg.localization.strategy,
        }
    clip: dict[str, Any] = {
        "OTIO_SCHEMA": "Clip.1",
        "name": seg.id,
        "source_range": _range_to_otio(seg.time_range),
        "metadata": {"videoforge": extras},
    }
    # media_reference：DaVinci/NLE 靠此重连媒体。source_ref 存在 → ExternalReference；
    # 否则 → MissingReference（NLE 打开时提示"离线媒体"而非静默丢字段）。§12 第 6 条硬要求。
    if seg.source_ref:
        clip["media_reference"] = {
            "OTIO_SCHEMA": "ExternalReference.1",
            "target_url": seg.source_ref,
            "available_range": None,
            "metadata": {"videoforge": {"source_ref": seg.source_ref}},
        }
    else:
        clip["media_reference"] = {
            "OTIO_SCHEMA": "MissingReference.1",
            "name": f"{seg.id}.missing",
            "metadata": {},
        }
    return clip


def to_otio_mapping(timeline: CreativeTimeline) -> dict[str, Any]:
    """CreativeTimeline → OTIO Timeline+Stack dict 结构（不写文件、不引 pip）。

    duration 显式带入 metadata.videoforge.duration_value —— 供 from_otio_mapping 精确还原，
    避免"末段留白"信息损失（源 duration 大于 segments 最远 end 时 max(end) 会漏掉尾部空白）。
    """
    otio_tracks: list[dict[str, Any]] = []
    for track in timeline.tracks:
        otio_tracks.append(
            {
                "OTIO_SCHEMA": "Track.1",
                "name": track.id,
                "kind": _TRACK_KIND_TO_OTIO_KIND[track.kind],
                "metadata": {"videoforge": {"kind": track.kind.value}},
                "children": [_segment_to_otio_clip(s) for s in track.segments],
            }
        )
    return {
        "OTIO_SCHEMA": "Timeline.1",
        "name": timeline.id,
        "global_start_time": _rt_to_otio(RationalTime(value=0, rate=timeline.rate)),
        "metadata": {
            "videoforge": {
                "project_id": timeline.project_id,
                "source_transcript_id": timeline.source_transcript_id,
                "source_asset_ids": list(timeline.source_asset_ids),
                "duration_value": timeline.duration.value,
            }
        },
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": timeline.id + ".stack",
            "children": otio_tracks,
        },
    }


def _rt_from_otio(d: dict[str, Any]) -> RationalTime:
    return RationalTime(value=int(d["value"]), rate=int(d["rate"]))


def _range_from_otio(d: dict[str, Any]) -> RationalTimeRange:
    return RationalTimeRange(start=_rt_from_otio(d["start_time"]),
                             duration=_rt_from_otio(d["duration"]))


def _clip_from_otio(clip: dict[str, Any]) -> Segment:
    from videoforge_contracts import LocalizationPolicy, SegmentEffect
    extras = (clip.get("metadata") or {}).get("videoforge") or {}
    localization = None
    if isinstance(extras.get("localization"), dict):
        loc = extras["localization"]
        localization = LocalizationPolicy(
            language=loc["language"], strategy=loc.get("strategy", "passthrough"),
        )
    effects = [
        SegmentEffect(kind=e["kind"], params=dict(e.get("params") or {}))
        for e in (extras.get("effects") or [])
    ]
    kwargs: dict[str, Any] = {
        "id": clip["name"], "time_range": _range_from_otio(clip["source_range"]),
    }
    for k in _SEGMENT_EXTRA_KEYS:
        if k in extras:
            kwargs[k] = extras[k]
    kwargs["effects"] = effects
    if localization is not None:
        kwargs["localization"] = localization
    return Segment(**kwargs)


def from_otio_mapping(data: dict[str, Any], *, created_at) -> CreativeTimeline:
    """OTIO dict → CreativeTimeline，扩展字段从 metadata.videoforge 回填（往返 semantic 保持）。"""
    stack = data["tracks"]
    root_meta = (data.get("metadata") or {}).get("videoforge") or {}
    tracks: list[Track] = []
    for otio_track in stack.get("children", []):
        vf = (otio_track.get("metadata") or {}).get("videoforge") or {}
        track_kind = TrackKind(vf["kind"])  # 严格：反向映射从 metadata 取，不猜
        segs = [_clip_from_otio(c) for c in otio_track.get("children", [])]
        tracks.append(Track(id=otio_track["name"], kind=track_kind, segments=segs))
    rate = int(data["global_start_time"]["rate"])
    # duration 优先从 metadata.videoforge.duration_value 精确还原（保末段留白）；
    # 缺该字段时退化为 max(segment end)，无 segment 时降为 0——兼容外部产出的 OTIO dict。
    max_end = 0
    for t in tracks:
        for s in t.segments:
            max_end = max(max_end, s.time_range.start.value + s.time_range.duration.value)
    duration_value = root_meta.get("duration_value", max_end)
    return CreativeTimeline(
        id=data["name"],
        project_id=root_meta.get("project_id"),
        rate=rate,
        duration=RationalTime(value=duration_value, rate=rate),
        tracks=tracks,
        source_transcript_id=root_meta.get("source_transcript_id"),
        source_asset_ids=list(root_meta.get("source_asset_ids") or []),
        created_at=created_at,
    )
