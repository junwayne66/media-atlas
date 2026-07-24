"""音频合成计划装配 + 护栏（docs/modules/43 §9）。纯函数，可复现。

§9 分轨合成规则被编码进护栏 `validate_audio_mix_plan`：

- 分轨：ORIGINAL_VOICE / VOICE_DUB / MUSIC / SFX / AMBIENCE。
- **Ducking 以语音活动为 sidechain**（`VOICE_ACTIVITY`），避免"每个切点泵动"
  （`CUT_POINT` → 护栏告警 `DUCKING_CUT_POINT`）。
- 语音永远在上：被 Ducking 的应是 MUSIC/AMBIENCE，触发源必须是**人声轨**——
  `VOICE_DUCKED`（人声被压）与 `DUCKED_BY_NON_VOICE`（触发源非人声）都拦。
- 响度：LoudnessTarget（LUFS + True Peak），True Peak Gate 由 QA（VF-309）兜底 BLOCKER。
- Room Tone：配音段之间避免"绝对静音"（可选 AMBIENCE 轨/room_tone_artifact_id）。

`build_audio_mix_plan` 给出"人声在上、音乐被语音活动 Ducking"的合规默认装配。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    AudioMixPlan,
    AudioMixTrack,
    AudioMixTrackKind,
    DuckingPolicy,
    DuckingSidechain,
    LoudnessTarget,
)

# 会被 Ducking 压低的轨（背景类）；人声轨作为 sidechain 触发源
_VOICE_KINDS = frozenset({
    AudioMixTrackKind.ORIGINAL_VOICE, AudioMixTrackKind.VOICE_DUB,
})
_DUCKABLE_KINDS = frozenset({
    AudioMixTrackKind.MUSIC, AudioMixTrackKind.AMBIENCE,
})


class AudioMixIssueKind(StrEnum):
    EMPTY_MIX = "EMPTY_MIX"
    NO_VOICE_TRACK = "NO_VOICE_TRACK"  # 既无 VOICE_DUB 也无 ORIGINAL_VOICE
    # §9：Ducking 必须以语音活动为 sidechain；切点触发会泵动
    DUCKING_CUT_POINT = "DUCKING_CUT_POINT"
    DUCKING_WITHOUT_POLICY = "DUCKING_WITHOUT_POLICY"  # 轨声明被 duck 但 plan.ducking 缺失
    DUCKED_BY_NON_VOICE = "DUCKED_BY_NON_VOICE"  # 触发源不是人声轨
    VOICE_DUCKED = "VOICE_DUCKED"  # 人声轨被压（反了优先级）
    TRACK_OUT_OF_BOUNDS = "TRACK_OUT_OF_BOUNDS"  # 轨 end 超 total_duration_ms


@dataclass(frozen=True)
class AudioMixIssue:
    kind: AudioMixIssueKind
    ref: str  # track id 或 plan id
    detail: str


def default_ducking_policy() -> DuckingPolicy:
    """§9 合规默认：语音活动 sidechain。"""
    return DuckingPolicy(
        sidechain=DuckingSidechain.VOICE_ACTIVITY,
        threshold_db=-20.0, ratio=8.0,
        attack_ms=20, release_ms=300, reduction_db=-8.0,
    )


def build_audio_mix_plan(
    *,
    id: str,
    created_at: datetime,
    voice_track: AudioMixTrack,
    background_tracks: list[AudioMixTrack] | None = None,
    loudness_target: LoudnessTarget | None = None,
    ducking: DuckingPolicy | None = None,
    room_tone_artifact_id: str | None = None,
    total_duration_ms: int | None = None,
) -> AudioMixPlan:
    """装配一份"人声在上、背景轨被人声活动 Ducking"的合规 `AudioMixPlan`。

    - `voice_track`：主人声轨（一般 VOICE_DUB）；作为 Ducking 的 sidechain 触发源。
    - `background_tracks`：MUSIC/AMBIENCE 等；每条 MUSIC/AMBIENCE 自动 `ducked_by=voice_track.id`
      （SFX 不自动压）。已显式设了 `ducked_by` 的尊重原值。
    - `total_duration_ms`：缺省取所有轨 end 的最大值。
    """
    background = list(background_tracks or [])
    ducking = ducking or default_ducking_policy()
    loudness_target = loudness_target or LoudnessTarget()

    wired: list[AudioMixTrack] = []
    for t in background:
        if t.kind in _DUCKABLE_KINDS and t.ducked_by is None and t.id != voice_track.id:
            wired.append(t.model_copy(update={"ducked_by": voice_track.id}))
        else:
            wired.append(t)

    tracks = [voice_track, *wired]
    if total_duration_ms is None:
        total_duration_ms = max((t.end_ms for t in tracks), default=0)
    # AudioMixPlan.total_duration_ms 要求 > 0
    total_duration_ms = max(total_duration_ms, 1)

    return AudioMixPlan(
        id=id,
        tracks=tracks,
        ducking=ducking,
        loudness_target=loudness_target,
        room_tone_artifact_id=room_tone_artifact_id,
        total_duration_ms=total_duration_ms,
        created_at=created_at,
    )


def validate_audio_mix_plan(plan: AudioMixPlan) -> list[AudioMixIssue]:
    """§9 音频合成护栏；返回全部违规（空 = 通过）。"""
    issues: list[AudioMixIssue] = []
    by_id = {t.id: t for t in plan.tracks}

    if not plan.tracks:
        issues.append(AudioMixIssue(
            AudioMixIssueKind.EMPTY_MIX, plan.id, "没有任何音轨",
        ))
        return issues  # 空计划后续检查无意义

    has_voice = any(t.kind in _VOICE_KINDS for t in plan.tracks)
    if not has_voice:
        issues.append(AudioMixIssue(
            AudioMixIssueKind.NO_VOICE_TRACK, plan.id,
            "计划无 VOICE_DUB / ORIGINAL_VOICE 人声轨",
        ))

    # Ducking sidechain：切点触发会泵动
    if plan.ducking is not None and (
        plan.ducking.sidechain is DuckingSidechain.CUT_POINT
    ):
        issues.append(AudioMixIssue(
            AudioMixIssueKind.DUCKING_CUT_POINT, plan.id,
            "Ducking sidechain=CUT_POINT 会在每个切点泵动；应改用 VOICE_ACTIVITY（§9）",
        ))

    for t in plan.tracks:
        # 轨越界
        if t.end_ms > plan.total_duration_ms:
            issues.append(AudioMixIssue(
                AudioMixIssueKind.TRACK_OUT_OF_BOUNDS, t.id,
                f"轨 end_ms={t.end_ms} 超 total_duration_ms={plan.total_duration_ms}",
            ))
        if t.ducked_by is None:
            continue
        # 声明被 duck 但没有 ducking 策略
        if plan.ducking is None:
            issues.append(AudioMixIssue(
                AudioMixIssueKind.DUCKING_WITHOUT_POLICY, t.id,
                f"轨声明 ducked_by={t.ducked_by!r} 但 plan.ducking 缺失",
            ))
        # 配音轨被压（反优先级）。注意：ORIGINAL_VOICE 被 VOICE_DUB 压是 §9 允许的
        # （替换配音时降低原声），故只拦 VOICE_DUB 被 Ducking。
        if t.kind is AudioMixTrackKind.VOICE_DUB:
            issues.append(AudioMixIssue(
                AudioMixIssueKind.VOICE_DUCKED, t.id,
                f"配音轨 {t.id!r} 不应被 Ducking——目标语言配音须在上",
            ))
        # 触发源必须是人声轨（合同已保证 ducked_by 指向存在的轨）
        source = by_id.get(t.ducked_by)
        if source is not None and source.kind not in _VOICE_KINDS:
            issues.append(AudioMixIssue(
                AudioMixIssueKind.DUCKED_BY_NON_VOICE, t.id,
                f"轨 {t.id!r} 的 Ducking 触发源 {source.id!r}（{source.kind.value}）"
                "不是人声轨；sidechain 应由人声活动驱动（§9）",
            ))
    return issues


def is_valid_audio_mix_plan(plan: AudioMixPlan) -> bool:
    return not validate_audio_mix_plan(plan)
