"""代表帧选择：覆盖各触发源、近邻合并、封顶不逐帧、低置信优先、纯可重放。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    BBox,
    FrameSampleReason,
    TextObservation,
    TextTrack,
    TextTrackKind,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
)
from videoforge_domain import select_representative_frames

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _select(**over):
    kwargs = dict(analysis_id="va-1", created_at=_T0, duration_ms=30000)
    kwargs.update(over)
    return select_representative_frames(**kwargs)


def _track(start, low=False) -> TextTrack:
    return TextTrack(
        id=f"t{start}", kind=TextTrackKind.CAPTION, text="字", start_ms=start, end_ms=start + 500,
        confidence=0.4 if low else 0.9, low_confidence=low,
        observations=[TextObservation(
            frame_time_ms=start, bbox=BBox(x=0.2, y=0.82, w=0.6, h=0.08), text="字", confidence=0.9
        )],
    )


def _transcript(segments) -> Transcript:
    return Transcript(
        id="tr", language="zh-CN", segments=segments,
        models=TranscriptModels(asr_provider="asr.x"), created_at=_T0,
    )


def _seg(sid, start, speaker, low=False) -> TranscriptSegment:
    return TranscriptSegment(
        id=sid, start_ms=start, end_ms=start + 1000, speaker_id=speaker,
        language="zh-CN", text="…", confidence=0.4 if low else 0.9, low_confidence=low,
    )


def test_keyframe_always_present() -> None:
    va = _select()
    assert va.frames[0].frame_time_ms == 0
    assert FrameSampleReason.KEYFRAME in va.frames[0].reasons
    assert va.sampling_policy == "representative@v1"
    assert va.vlm_provider is None  # 仅选帧，未分析


def test_scene_cuts_become_frames() -> None:
    va = _select(scene_cuts=(3.0, 10.0), periodic_interval_ms=999999)
    times = [f.frame_time_ms for f in va.frames]
    assert 3000 in times and 10000 in times
    cut = next(f for f in va.frames if f.frame_time_ms == 3000)
    assert FrameSampleReason.SCENE_CUT in cut.reasons


def test_text_change_and_low_confidence() -> None:
    va = _select(text_tracks=(_track(4000), _track(9000, low=True)), periodic_interval_ms=999999)
    lo = next(f for f in va.frames if f.frame_time_ms == 9000)
    assert FrameSampleReason.LOW_CONFIDENCE in lo.reasons
    assert FrameSampleReason.TEXT_CHANGE in lo.reasons


def test_speaker_change() -> None:
    t = _transcript([_seg("a", 0, "spk_0"), _seg("b", 5000, "spk_1"), _seg("c", 9000, "spk_1")])
    va = _select(transcript=t, periodic_interval_ms=999999)
    times = {f.frame_time_ms for f in va.frames}
    assert 5000 in times  # 换人处采样
    assert 9000 not in times  # 同一人续说不采
    sc = next(f for f in va.frames if f.frame_time_ms == 5000)
    assert FrameSampleReason.SPEAKER_CHANGE in sc.reasons


def test_near_frames_merge_reasons() -> None:
    # 场景切点与文本轨在 300ms 内 → 合并为一帧带两个 reason
    va = _select(scene_cuts=(3.0,), text_tracks=(_track(3200),), periodic_interval_ms=999999,
                 merge_window_ms=500)
    near = [f for f in va.frames if 2900 <= f.frame_time_ms <= 3300]
    assert len(near) == 1
    assert FrameSampleReason.SCENE_CUT in near[0].reasons
    assert FrameSampleReason.TEXT_CHANGE in near[0].reasons


def test_cap_never_per_frame() -> None:
    # 密集场景切点（每 0.1s，300 个）→ 选帧数封顶，绝不逐帧
    cuts = tuple(i * 0.1 for i in range(1, 300))
    va = _select(duration_ms=30000, scene_cuts=cuts, max_frames=40)
    assert len(va.frames) <= 40
    assert va.frames[0].frame_time_ms == 0  # KEYFRAME 仍在（最高优先级不被丢）


def test_cap_keeps_high_priority_over_periodic() -> None:
    # 超额时优先丢周期性，保低置信
    cuts = tuple(i * 0.1 for i in range(1, 100))
    lo_tracks = tuple(_track(1000 * i, low=True) for i in range(1, 20))
    va = _select(duration_ms=60000, scene_cuts=cuts, text_tracks=lo_tracks,
                 periodic_interval_ms=1000, max_frames=30)
    reasons = {r for f in va.frames for r in f.reasons}
    assert FrameSampleReason.LOW_CONFIDENCE in reasons  # 低置信被保留
    assert len(va.frames) <= 30


def test_pure_and_replayable() -> None:
    args = dict(scene_cuts=(3.0, 10.0), text_tracks=(_track(4000, low=True),))
    a = _select(**args)
    b = _select(**args)
    assert a.model_dump() == b.model_dump()


def test_frames_sorted_by_time() -> None:
    va = _select(scene_cuts=(10.0, 3.0, 7.0), periodic_interval_ms=999999)
    times = [f.frame_time_ms for f in va.frames]
    assert times == sorted(times)
