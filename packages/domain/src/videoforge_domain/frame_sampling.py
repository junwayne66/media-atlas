"""代表帧选择（docs/modules/41 §9）。纯函数，逐位可重放。

VLM 只分析代表帧——本函数综合场景切点、文本轨出现、说话人切换、上游低置信片段选出信息量
最大的一小撮帧，近邻合并，并**封顶 max_frames**：无论视频多长/切点多密，选帧数恒有上界，
从结构上杜绝逐帧云调用（成本红线）。低置信片段被优先保留，交 VLM 消歧。

id/created_at 由调用方传入（不在域内取时钟），保证纯与可重放。
"""

from __future__ import annotations

from datetime import datetime

from videoforge_contracts import (
    FrameAnalysis,
    FrameSampleReason,
    TextTrack,
    Transcript,
    VisualAnalysis,
)

SAMPLING_POLICY = "representative@v1"

# reason 重要度（越小越保留）。封顶时优先保高优先级；同一帧取最重要 reason 定优先级。
_PRIORITY: dict[FrameSampleReason, int] = {
    FrameSampleReason.KEYFRAME: 0,
    FrameSampleReason.SCENE_CUT: 1,
    FrameSampleReason.LOW_CONFIDENCE: 2,
    FrameSampleReason.SPEAKER_CHANGE: 3,
    FrameSampleReason.TEXT_CHANGE: 4,
    FrameSampleReason.PERIODIC: 5,
}


def _candidates(
    duration_ms: int,
    scene_cuts: tuple[float, ...],
    text_tracks: tuple[TextTrack, ...],
    transcript: Transcript | None,
    periodic_interval_ms: int,
) -> list[tuple[int, FrameSampleReason]]:
    out: list[tuple[int, FrameSampleReason]] = [(0, FrameSampleReason.KEYFRAME)]
    for c in scene_cuts:
        t = int(round(c * 1000))
        if 0 <= t <= duration_ms:
            out.append((t, FrameSampleReason.SCENE_CUT))
    for tr in text_tracks:
        out.append((tr.start_ms, FrameSampleReason.TEXT_CHANGE))
        if tr.low_confidence:
            out.append((tr.start_ms, FrameSampleReason.LOW_CONFIDENCE))
    if transcript is not None:
        prev_speaker: str | None = None
        for i, seg in enumerate(transcript.segments):
            if i > 0 and seg.speaker_id != prev_speaker:
                out.append((seg.start_ms, FrameSampleReason.SPEAKER_CHANGE))
            prev_speaker = seg.speaker_id
            if seg.low_confidence:
                out.append((seg.start_ms, FrameSampleReason.LOW_CONFIDENCE))
    t = periodic_interval_ms
    while t < duration_ms:
        out.append((t, FrameSampleReason.PERIODIC))
        t += periodic_interval_ms
    return out


def select_representative_frames(
    *,
    analysis_id: str,
    created_at: datetime,
    duration_ms: int,
    scene_cuts: tuple[float, ...] = (),
    text_tracks: tuple[TextTrack, ...] = (),
    transcript: Transcript | None = None,
    source_artifact_id: str | None = None,
    max_frames: int = 40,
    periodic_interval_ms: int = 5000,
    merge_window_ms: int = 500,
) -> VisualAnalysis:
    """选代表帧 → VisualAnalysis（caption 未填）。选帧数 ≤ max_frames，绝不逐帧。"""
    cands = _candidates(duration_ms, scene_cuts, text_tracks, transcript, periodic_interval_ms)
    # 按时间 + 优先级排序，近邻窗口内合并（同一帧多原因）
    cands.sort(key=lambda c: (c[0], _PRIORITY[c[1]]))
    groups: list[tuple[int, set[FrameSampleReason]]] = []
    for time_ms, reason in cands:
        if groups and time_ms - groups[-1][0] <= merge_window_ms:
            groups[-1][1].add(reason)
        else:
            groups.append((time_ms, {reason}))

    # 封顶：保高优先级（KEYFRAME 恒在），丢低优先级（周期性优先被丢）
    if len(groups) > max_frames:
        groups = sorted(groups, key=lambda g: (min(_PRIORITY[r] for r in g[1]), g[0]))[:max_frames]

    frames = [
        FrameAnalysis(
            frame_time_ms=time_ms,
            reasons=sorted(reasons, key=lambda r: _PRIORITY[r]),
        )
        for time_ms, reasons in sorted(groups, key=lambda g: g[0])
    ]
    return VisualAnalysis(
        id=analysis_id,
        source_artifact_id=source_artifact_id,
        frames=frames,
        sampling_policy=SAMPLING_POLICY,
        created_at=created_at,
    )
