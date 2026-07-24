"""VF-405 音频合成 domain 测试：§9 分轨装配 + Ducking 语义护栏。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    AudioMixPlan,
    AudioMixTrack,
    AudioMixTrackKind,
    DuckingPolicy,
    DuckingSidechain,
    LoudnessTarget,
)
from videoforge_domain import (
    AudioMixIssueKind,
    build_audio_mix_plan,
    default_ducking_policy,
    is_valid_audio_mix_plan,
    validate_audio_mix_plan,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _track(tid: str, kind: AudioMixTrackKind, *, end: int = 8000,
           start: int = 0, ducked_by: str | None = None) -> AudioMixTrack:
    return AudioMixTrack(
        id=tid, kind=kind, start_ms=start, end_ms=end, ducked_by=ducked_by,
    )


# --- build_audio_mix_plan ---------------------------------------------------

def test_default_ducking_is_voice_activity():
    assert default_ducking_policy().sidechain is DuckingSidechain.VOICE_ACTIVITY


def test_build_wires_music_and_ambience_ducked_by_voice():
    voice = _track("dub", AudioMixTrackKind.VOICE_DUB)
    music = _track("mus", AudioMixTrackKind.MUSIC)
    amb = _track("amb", AudioMixTrackKind.AMBIENCE)
    plan = build_audio_mix_plan(
        id="am", created_at=_T0, voice_track=voice,
        background_tracks=[music, amb],
    )
    by_id = {t.id: t for t in plan.tracks}
    assert by_id["mus"].ducked_by == "dub"
    assert by_id["amb"].ducked_by == "dub"
    assert is_valid_audio_mix_plan(plan)


def test_build_does_not_auto_duck_sfx():
    voice = _track("dub", AudioMixTrackKind.VOICE_DUB)
    sfx = _track("sfx", AudioMixTrackKind.SFX)
    plan = build_audio_mix_plan(
        id="am", created_at=_T0, voice_track=voice, background_tracks=[sfx],
    )
    assert {t.id: t for t in plan.tracks}["sfx"].ducked_by is None
    assert is_valid_audio_mix_plan(plan)


def test_build_respects_explicit_ducked_by():
    voice = _track("dub", AudioMixTrackKind.VOICE_DUB)
    music = _track("mus", AudioMixTrackKind.MUSIC, ducked_by="dub")
    plan = build_audio_mix_plan(
        id="am", created_at=_T0, voice_track=voice, background_tracks=[music],
    )
    assert {t.id: t for t in plan.tracks}["mus"].ducked_by == "dub"


def test_build_derives_total_duration_from_max_end():
    voice = _track("dub", AudioMixTrackKind.VOICE_DUB, end=8200)
    music = _track("mus", AudioMixTrackKind.MUSIC, end=9000)
    plan = build_audio_mix_plan(
        id="am", created_at=_T0, voice_track=voice, background_tracks=[music],
    )
    assert plan.total_duration_ms == 9000


def test_lowering_original_voice_under_dub_is_allowed():
    # §9：替换配音时降低原声是允许的——ORIGINAL_VOICE 被 dub 压不应报错
    plan = AudioMixPlan(
        id="am",
        tracks=[
            _track("dub", AudioMixTrackKind.VOICE_DUB),
            _track("orig", AudioMixTrackKind.ORIGINAL_VOICE, ducked_by="dub"),
        ],
        ducking=default_ducking_policy(),
        loudness_target=LoudnessTarget(),
        total_duration_ms=8000, created_at=_T0,
    )
    assert validate_audio_mix_plan(plan) == []


# --- 护栏 -------------------------------------------------------------------

def test_flags_empty_mix():
    plan = AudioMixPlan(
        id="am", tracks=[], loudness_target=LoudnessTarget(),
        total_duration_ms=1000, created_at=_T0,
    )
    kinds = {i.kind for i in validate_audio_mix_plan(plan)}
    assert AudioMixIssueKind.EMPTY_MIX in kinds


def test_flags_no_voice_track():
    plan = AudioMixPlan(
        id="am",
        tracks=[_track("mus", AudioMixTrackKind.MUSIC)],
        loudness_target=LoudnessTarget(),
        total_duration_ms=8000, created_at=_T0,
    )
    kinds = {i.kind for i in validate_audio_mix_plan(plan)}
    assert AudioMixIssueKind.NO_VOICE_TRACK in kinds


def test_flags_cut_point_ducking():
    plan = AudioMixPlan(
        id="am",
        tracks=[_track("dub", AudioMixTrackKind.VOICE_DUB)],
        ducking=DuckingPolicy(sidechain=DuckingSidechain.CUT_POINT),
        loudness_target=LoudnessTarget(),
        total_duration_ms=8000, created_at=_T0,
    )
    kinds = {i.kind for i in validate_audio_mix_plan(plan)}
    assert AudioMixIssueKind.DUCKING_CUT_POINT in kinds


def test_flags_ducking_without_policy():
    plan = AudioMixPlan(
        id="am",
        tracks=[
            _track("dub", AudioMixTrackKind.VOICE_DUB),
            _track("mus", AudioMixTrackKind.MUSIC, ducked_by="dub"),
        ],
        ducking=None,  # 声明被压但无策略
        loudness_target=LoudnessTarget(),
        total_duration_ms=8000, created_at=_T0,
    )
    kinds = {i.kind for i in validate_audio_mix_plan(plan)}
    assert AudioMixIssueKind.DUCKING_WITHOUT_POLICY in kinds


def test_flags_ducked_by_non_voice():
    plan = AudioMixPlan(
        id="am",
        tracks=[
            _track("dub", AudioMixTrackKind.VOICE_DUB),
            _track("m1", AudioMixTrackKind.MUSIC),
            _track("m2", AudioMixTrackKind.MUSIC, ducked_by="m1"),  # 触发源非人声
        ],
        ducking=default_ducking_policy(),
        loudness_target=LoudnessTarget(),
        total_duration_ms=8000, created_at=_T0,
    )
    issues = validate_audio_mix_plan(plan)
    non_voice = [i for i in issues
                  if i.kind is AudioMixIssueKind.DUCKED_BY_NON_VOICE]
    assert len(non_voice) == 1
    assert non_voice[0].ref == "m2"


def test_flags_voice_dub_ducked():
    plan = AudioMixPlan(
        id="am",
        tracks=[
            _track("mus", AudioMixTrackKind.MUSIC),
            _track("dub", AudioMixTrackKind.VOICE_DUB, ducked_by="mus"),  # 配音被压
        ],
        ducking=default_ducking_policy(),
        loudness_target=LoudnessTarget(),
        total_duration_ms=8000, created_at=_T0,
    )
    kinds = {i.kind for i in validate_audio_mix_plan(plan)}
    assert AudioMixIssueKind.VOICE_DUCKED in kinds


def test_flags_track_out_of_bounds():
    plan = AudioMixPlan(
        id="am",
        tracks=[_track("dub", AudioMixTrackKind.VOICE_DUB, end=9000)],
        loudness_target=LoudnessTarget(),
        total_duration_ms=8000, created_at=_T0,  # 轨 9000 > 8000
    )
    kinds = {i.kind for i in validate_audio_mix_plan(plan)}
    assert AudioMixIssueKind.TRACK_OUT_OF_BOUNDS in kinds


def test_clean_plan_has_no_issues():
    plan = AudioMixPlan(
        id="am",
        tracks=[
            _track("dub", AudioMixTrackKind.VOICE_DUB),
            _track("mus", AudioMixTrackKind.MUSIC, ducked_by="dub"),
        ],
        ducking=default_ducking_policy(),
        loudness_target=LoudnessTarget(),
        total_duration_ms=8000, created_at=_T0,
    )
    assert validate_audio_mix_plan(plan) == []
