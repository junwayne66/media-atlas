"""Blueprint 候选生成 + 校验护栏（docs/modules/41 §10）。纯函数。

- build_candidate_rhetorical_beats：从转录段铺满时间线的候选节拍（全 UNCLASSIFIED，
  含语音间隙），时间范围由程序提供——融合 Provider（LLM）只在这些候选内改 kind、抽 claim，
  绝不编造时间戳（§10.2）。
- build_visual_beats：VLM 标签 → VisualBeat（人物/屏录/产品/图卡…）。
- validate_blueprint：护栏——时间在时长内且单调、每 Claim 有非空且引用真实 evidence、
  节拍 claim_ids 引用真实 Claim、rhetorical 覆盖率 ≥ 阈值。任一违规产出 BlueprintIssue。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from videoforge_contracts import (
    RhetoricalBeat,
    RhetoricalBeatKind,
    Transcript,
    VideoBlueprint,
    VisualAnalysis,
    VisualBeat,
    VisualBeatKind,
)

_MIN_COVERAGE = 0.9

# VLM 标签 → 视觉节拍类型（首个命中优先）
_LABEL_TO_VISUAL: tuple[tuple[str, VisualBeatKind], ...] = (
    ("screen_record", VisualBeatKind.SCREEN_RECORD),
    ("screen", VisualBeatKind.SCREEN_RECORD),
    ("person", VisualBeatKind.PERSON),
    ("face", VisualBeatKind.PERSON),
    ("product", VisualBeatKind.PRODUCT),
    ("chart", VisualBeatKind.CARD),
    ("card", VisualBeatKind.CARD),
    ("text", VisualBeatKind.CARD),
    ("broll", VisualBeatKind.B_ROLL),
)


def build_candidate_rhetorical_beats(
    transcript: Transcript | None, duration_ms: int, *, id_prefix: str = "rb"
) -> list[RhetoricalBeat]:
    """转录段 → 铺满 [0, duration] 的候选节拍（全 UNCLASSIFIED）。融合只在其上改 kind。"""
    segs = (
        sorted((s.start_ms, s.end_ms) for s in transcript.segments)
        if (transcript and transcript.segments)
        else []
    )
    spans: list[tuple[int, int]] = []
    cursor = 0
    for raw_start, raw_end in segs:
        # 钳到 [cursor, duration]——上游段时间可能超出目标时长，绝不产出越界候选
        start = max(cursor, min(raw_start, duration_ms))
        end = max(0, min(raw_end, duration_ms))
        if end <= start:
            continue  # 越界或钳后零长
        if start > cursor:
            spans.append((cursor, start))  # 语音间隙
        spans.append((start, end))  # 语音段
        cursor = max(cursor, end)
    if cursor < duration_ms:
        spans.append((cursor, duration_ms))  # 尾部
    if not spans:
        spans = [(0, duration_ms)]
    return [
        RhetoricalBeat(
            id=f"{id_prefix}-{i}", kind=RhetoricalBeatKind.UNCLASSIFIED, start_ms=s, end_ms=e
        )
        for i, (s, e) in enumerate(spans)
    ]


def _label_kind(labels: list[str]) -> VisualBeatKind:
    lower = {label_.lower() for label_ in labels}
    for marker, kind in _LABEL_TO_VISUAL:
        if any(marker in label_ for label_ in lower):
            return kind
    return VisualBeatKind.UNKNOWN


def build_visual_beats(
    visual_analysis: VisualAnalysis, duration_ms: int, *, id_prefix: str = "vb"
) -> list[VisualBeat]:
    """已分析的代表帧 → VisualBeat，每帧跨到下一帧时间（末帧到 duration）。"""
    frames = sorted(visual_analysis.frames, key=lambda f: f.frame_time_ms)
    beats: list[VisualBeat] = []
    for i, f in enumerate(frames):
        if f.frame_time_ms > duration_ms:
            continue  # 越界帧跳过——不能落 beat（上游帧时间可能超出目标时长）
        raw_end = frames[i + 1].frame_time_ms if i + 1 < len(frames) else duration_ms
        end = min(max(raw_end, f.frame_time_ms), duration_ms)
        beats.append(
            VisualBeat(
                id=f"{id_prefix}-{len(beats)}",
                kind=_label_kind(f.labels),
                start_ms=f.frame_time_ms,
                end_ms=end,
                frame_time_ms=f.frame_time_ms,
            )
        )
    return beats


# —— 校验护栏 ——


class BlueprintIssueKind(StrEnum):
    TIME_OUT_OF_RANGE = "TIME_OUT_OF_RANGE"
    TIME_NOT_MONOTONIC = "TIME_NOT_MONOTONIC"
    CLAIM_NO_EVIDENCE = "CLAIM_NO_EVIDENCE"
    EVIDENCE_REF_INVALID = "EVIDENCE_REF_INVALID"
    EVIDENCE_OUT_OF_RANGE = "EVIDENCE_OUT_OF_RANGE"
    BEAT_CLAIM_REF_INVALID = "BEAT_CLAIM_REF_INVALID"
    LOW_COVERAGE = "LOW_COVERAGE"


@dataclass(frozen=True)
class BlueprintIssue:
    kind: BlueprintIssueKind
    ref: str
    detail: str


def _union_length(beats: list[RhetoricalBeat]) -> int:
    ranges = sorted((b.start_ms, b.end_ms) for b in beats)
    total = 0
    cur_start: int | None = None
    cur_end: int | None = None
    for s, e in ranges:
        if cur_end is None or s > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start  # type: ignore[operator]
            cur_start, cur_end = s, e
        else:
            cur_end = max(cur_end, e)
    if cur_end is not None:
        total += cur_end - cur_start  # type: ignore[operator]
    return total


def validate_blueprint(
    blueprint: VideoBlueprint,
    *,
    transcript_segment_ids: set[str],
    text_track_ids: set[str],
    min_coverage: float = _MIN_COVERAGE,
) -> list[BlueprintIssue]:
    """护栏校验；返回全部违规（空 = 通过）。"""
    issues: list[BlueprintIssue] = []
    duration = blueprint.duration_ms
    claim_ids = {c.id for c in blueprint.claims}

    for b in [*blueprint.rhetorical_beats, *blueprint.visual_beats]:
        if b.start_ms < 0 or b.end_ms > duration:
            issues.append(
                BlueprintIssue(
                    BlueprintIssueKind.TIME_OUT_OF_RANGE, b.id, f"end {b.end_ms} > {duration}"
                )
            )

    starts = [b.start_ms for b in blueprint.rhetorical_beats]
    if starts != sorted(starts):
        issues.append(BlueprintIssue(BlueprintIssueKind.TIME_NOT_MONOTONIC, "rhetorical_beats", ""))

    for c in blueprint.claims:
        if not c.evidence:  # 合同已挡（min_length=1），冗余护栏
            issues.append(BlueprintIssue(BlueprintIssueKind.CLAIM_NO_EVIDENCE, c.id, ""))
        for ev in c.evidence:
            valid = transcript_segment_ids if ev.kind == "transcript" else text_track_ids
            if ev.ref_id not in valid:
                issues.append(
                    BlueprintIssue(
                        BlueprintIssueKind.EVIDENCE_REF_INVALID, c.id, f"{ev.kind}:{ev.ref_id}"
                    )
                )
            if ev.end_ms > duration:
                issues.append(BlueprintIssue(BlueprintIssueKind.EVIDENCE_OUT_OF_RANGE, c.id, ""))

    for b in blueprint.rhetorical_beats:
        for cid in b.claim_ids:
            if cid not in claim_ids:
                issues.append(BlueprintIssue(BlueprintIssueKind.BEAT_CLAIM_REF_INVALID, b.id, cid))

    if duration > 0:
        coverage = _union_length(blueprint.rhetorical_beats) / duration
        if coverage < min_coverage:
            issues.append(
                BlueprintIssue(
                    BlueprintIssueKind.LOW_COVERAGE,
                    "rhetorical_beats",
                    f"{coverage:.3f} < {min_coverage}",
                )
            )
    return issues


def is_valid_blueprint(
    blueprint: VideoBlueprint,
    *,
    transcript_segment_ids: set[str],
    text_track_ids: set[str],
    min_coverage: float = _MIN_COVERAGE,
) -> bool:
    return not validate_blueprint(
        blueprint,
        transcript_segment_ids=transcript_segment_ids,
        text_track_ids=text_track_ids,
        min_coverage=min_coverage,
    )


def coverage_ratio(blueprint: VideoBlueprint) -> float:
    """rhetorical 节拍的时间覆盖率（union / duration）。"""
    if blueprint.duration_ms <= 0:
        return 0.0
    return _union_length(blueprint.rhetorical_beats) / blueprint.duration_ms
