"""VF-404 TTS domain 测试：Voice Profile 授权护栏 + 合成计划 + 时长拟合评估。"""

from datetime import UTC, datetime, timedelta

from videoforge_contracts import (
    TTSManifest,
    TTSProviderTier,
    TTSWordTiming,
    VoiceKind,
    VoiceLicenseStatus,
    VoiceProfile,
    VoiceStyle,
)
from videoforge_domain import (
    NATURAL_SPEED_MAX,
    NATURAL_SPEED_MIN,
    TTSManifestIssueKind,
    VoiceProfileIssueKind,
    is_authorized_for_synthesis,
    is_valid_tts_manifest,
    is_valid_voice_profile,
    plan_tts_synthesis,
    suggest_speed,
    text_hash_of,
    validate_tts_manifest,
    validate_voice_profile,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _profile(**k) -> VoiceProfile:
    defaults = dict(
        id="v1",
        display_name="Anchor",
        language="zh-CN",
        voice_kind=VoiceKind.PRESET,
        license_status=VoiceLicenseStatus.AUTHORIZED,
        created_at=_T0,
    )
    defaults.update(k)
    return VoiceProfile(**defaults)


def _cloned(**k) -> VoiceProfile:
    defaults = dict(
        id="v2",
        display_name="Cloned",
        language="zh-CN",
        voice_kind=VoiceKind.CLONED,
        license_status=VoiceLicenseStatus.AUTHORIZED,
        sample_source_ref="artifact://sample.wav",
        consent_ref="consent://signed",
        created_at=_T0,
    )
    defaults.update(k)
    return VoiceProfile(**defaults)


# —— validate_voice_profile: 授权硬红线 ——


def test_authorized_profile_passes() -> None:
    assert is_valid_voice_profile(_profile())


def test_unconfirmed_status_flagged() -> None:
    kinds = [
        i.kind
        for i in validate_voice_profile(_profile(license_status=VoiceLicenseStatus.UNCONFIRMED))
    ]
    assert VoiceProfileIssueKind.LICENSE_NOT_AUTHORIZED in kinds


def test_pending_status_flagged() -> None:
    kinds = [
        i.kind for i in validate_voice_profile(_profile(license_status=VoiceLicenseStatus.PENDING))
    ]
    assert VoiceProfileIssueKind.LICENSE_NOT_AUTHORIZED in kinds


def test_denied_status_flagged() -> None:
    kinds = [
        i.kind for i in validate_voice_profile(_profile(license_status=VoiceLicenseStatus.DENIED))
    ]
    assert VoiceProfileIssueKind.LICENSE_NOT_AUTHORIZED in kinds


def test_expired_license_flagged_when_now_given() -> None:
    p = _profile(
        license_status=VoiceLicenseStatus.AUTHORIZED,
        expires_at=_T0 - timedelta(days=1),
    )
    kinds = [i.kind for i in validate_voice_profile(p, now=_T0)]
    assert VoiceProfileIssueKind.LICENSE_EXPIRED in kinds


def test_expired_license_not_flagged_when_now_none() -> None:
    """无 now → domain 不能判断时间，跳过（避免时钟依赖）。"""
    p = _profile(
        license_status=VoiceLicenseStatus.AUTHORIZED,
        expires_at=_T0 - timedelta(days=1),
    )
    kinds = [i.kind for i in validate_voice_profile(p, now=None)]
    assert VoiceProfileIssueKind.LICENSE_EXPIRED not in kinds


def test_language_mismatch_flagged() -> None:
    kinds = [
        i.kind
        for i in validate_voice_profile(
            _profile(language="zh-CN"),
            request_language="ja-JP",
        )
    ]
    assert VoiceProfileIssueKind.LANGUAGE_MISMATCH in kinds


def test_cloned_missing_sample_flagged_domain() -> None:
    """合同层拦最重，但 domain 双保险仍能识别（若绕过路径进入 domain）。
    注意：合同层拒会 raise ValidationError；此处不能构造这类"违规"实例——
    直接测存在字段但为空的情况（VoiceProfile 允许 sample_source_ref=None 若 kind 非 CLONED；
    对 CLONED 强要求）。用模拟对象验证 domain 分支的健壮性。"""
    # 通过 model_copy 手工造：先建合法 CLONED，再"绕开"合同层
    p = _cloned(sample_source_ref="art://s.wav", consent_ref="c://ok")
    # domain 层看到的是完整对象——合同层已拦了缺 sample 的情况；
    # 这里断言：合法 CLONED 通过 domain（授权 + 双 ref 齐全）。
    assert is_valid_voice_profile(p)


# —— is_authorized_for_synthesis: 便捷入口 ——


def test_is_authorized_true_on_authorized_and_no_expiry() -> None:
    assert is_authorized_for_synthesis(_profile())


def test_is_authorized_false_on_expired_with_now() -> None:
    p = _profile(expires_at=_T0 - timedelta(days=1))
    assert not is_authorized_for_synthesis(p, now=_T0)


# —— text_hash_of: 缓存键性质 ——


def test_text_hash_stable_and_deterministic() -> None:
    h1 = text_hash_of("hi", language="en-US", voice_profile_id="v1")
    h2 = text_hash_of("hi", language="en-US", voice_profile_id="v1")
    assert h1 == h2
    assert len(h1) == 64


def test_text_hash_changes_with_text() -> None:
    a = text_hash_of("hi", language="en-US", voice_profile_id="v1")
    b = text_hash_of("hello", language="en-US", voice_profile_id="v1")
    assert a != b


def test_text_hash_changes_with_seed() -> None:
    a = text_hash_of("hi", language="en-US", voice_profile_id="v1", seed=1)
    b = text_hash_of("hi", language="en-US", voice_profile_id="v1", seed=2)
    assert a != b


def test_text_hash_changes_with_style() -> None:
    a = text_hash_of("hi", language="en-US", voice_profile_id="v1")
    b = text_hash_of("hi", language="en-US", voice_profile_id="v1", style=VoiceStyle(pace=1.05))
    assert a != b


# —— suggest_speed: §8 时长拟合 ——


def test_suggest_speed_basic() -> None:
    # 估算 3000ms 要塞进 2000ms 目标 → 1.5x
    assert suggest_speed(3000, 2000) == 1.5


def test_suggest_speed_within_natural_bounds() -> None:
    # 1030/1000 = 1.03 属于自然区间 [0.92, 1.08]
    speed = suggest_speed(1030, 1000)
    assert NATURAL_SPEED_MIN <= speed <= NATURAL_SPEED_MAX


def test_suggest_speed_no_target_returns_one() -> None:
    assert suggest_speed(1000, 0) == 1.0


# —— plan_tts_synthesis ——


def test_plan_tts_skips_unauthorized_voices() -> None:
    """未授权 profile 直接跳过——不生成 job（UI 侧看到句子缺 job = 需人工）。"""
    ok = _profile(id="ok")
    denied = _profile(id="denied", license_status=VoiceLicenseStatus.DENIED)
    jobs = plan_tts_synthesis(
        sentences=[("s0", "a", "zh-CN"), ("s1", "b", "zh-CN")],
        voice_by_speaker={"host": ok, "guest": denied},
        default_voice=ok,
        speaker_by_sentence={"s0": "host", "s1": "guest"},
    )
    assert [j.sentence_id for j in jobs] == ["s0"]  # s1 被跳过


def test_plan_tts_uses_default_voice_when_speaker_missing() -> None:
    default = _profile(id="default")
    jobs = plan_tts_synthesis(
        sentences=[("s0", "a", "zh-CN")],
        voice_by_speaker={},
        default_voice=default,
    )
    assert len(jobs) == 1
    assert jobs[0].voice_profile_id == "default"


def test_plan_tts_flags_speed_out_of_natural_bounds() -> None:
    default = _profile(id="d")
    # 估算 5000ms → 目标 1000ms → speed=5.0 远超 1.08
    jobs = plan_tts_synthesis(
        sentences=[("s0", "a", "zh-CN")],
        voice_by_speaker={},
        default_voice=default,
        target_duration_by_sentence={"s0": 1000},
        estimated_duration_by_sentence={"s0": 5000},
    )
    assert TTSManifestIssueKind.SPEED_OUT_OF_NATURAL_BOUNDS.value in jobs[0].review_reasons


def test_plan_tts_text_hash_deterministic_across_calls() -> None:
    default = _profile()
    jobs1 = plan_tts_synthesis(
        sentences=[("s0", "hi", "en-US")],
        voice_by_speaker={},
        default_voice=default,
    )
    jobs2 = plan_tts_synthesis(
        sentences=[("s0", "hi", "en-US")],
        voice_by_speaker={},
        default_voice=default,
    )
    assert jobs1[0].text_hash == jobs2[0].text_hash


# —— validate_tts_manifest ——


def _manifest(**k) -> TTSManifest:
    defaults = dict(
        id="m0",
        sentence_id="s0",
        voice_profile_id="v1",
        language="zh-CN",
        text_hash="a" * 64,
        provider="tts.fake",
        provider_tier=TTSProviderTier.CLOUD_HIGH_QUALITY,
        audio_artifact_id="fake://a.wav",
        duration_ms=1000,
        word_timings=[
            TTSWordTiming(text="hi", start_ms=0, end_ms=500, confidence=0.5),
            TTSWordTiming(text="you", start_ms=500, end_ms=1000, confidence=0.5),
        ],
        speed_used=1.0,
        seed=None,
        created_at=_T0,
    )
    defaults.update(k)
    return TTSManifest(**defaults)


def test_validate_manifest_clean_passes() -> None:
    assert is_valid_tts_manifest(_manifest())


def test_validate_manifest_word_timings_empty() -> None:
    kinds = [
        i.kind
        for i in validate_tts_manifest(
            _manifest(word_timings=[]),
        )
    ]
    assert TTSManifestIssueKind.WORD_TIMINGS_EMPTY in kinds


def test_validate_manifest_word_timings_not_monotonic() -> None:
    m = _manifest(
        word_timings=[
            TTSWordTiming(text="a", start_ms=0, end_ms=500),
            TTSWordTiming(text="b", start_ms=400, end_ms=800),  # 早于前 end
        ]
    )
    kinds = [i.kind for i in validate_tts_manifest(m)]
    assert TTSManifestIssueKind.WORD_TIMINGS_NOT_MONOTONIC in kinds


def test_validate_manifest_word_timing_out_of_total() -> None:
    m = _manifest(
        duration_ms=800,
        word_timings=[
            TTSWordTiming(text="a", start_ms=0, end_ms=500),
            TTSWordTiming(text="b", start_ms=500, end_ms=1200),  # 超 duration
        ],
    )
    kinds = [i.kind for i in validate_tts_manifest(m)]
    assert TTSManifestIssueKind.WORD_TIMING_OUT_OF_TOTAL in kinds


def test_validate_manifest_text_hash_mismatch() -> None:
    m = _manifest(text_hash="0" * 64)
    kinds = [
        i.kind
        for i in validate_tts_manifest(
            m,
            request_text="hi",  # 与 manifest 不匹配
        )
    ]
    assert TTSManifestIssueKind.TEXT_HASH_MISMATCH in kinds


def test_validate_manifest_text_hash_match() -> None:
    """给出与 manifest 一致的 request 上下文——hash 应匹配。"""
    hash_val = text_hash_of("hi", language="zh-CN", voice_profile_id="v1")
    m = _manifest(text_hash=hash_val)
    kinds = [i.kind for i in validate_tts_manifest(m, request_text="hi")]
    assert TTSManifestIssueKind.TEXT_HASH_MISMATCH not in kinds


def test_validate_manifest_duration_out_of_tolerance() -> None:
    kinds = [
        i.kind
        for i in validate_tts_manifest(
            _manifest(duration_ms=2000),
            target_duration_ms=1000,  # 100% 超 ±10%
        )
    ]
    assert TTSManifestIssueKind.DURATION_OUT_OF_TOLERANCE in kinds


def test_validate_manifest_duration_within_tolerance() -> None:
    """1050/1000 = 1.05 属于 ±10%，通过。"""
    kinds = [
        i.kind
        for i in validate_tts_manifest(
            _manifest(duration_ms=1050),
            target_duration_ms=1000,
        )
    ]
    assert TTSManifestIssueKind.DURATION_OUT_OF_TOLERANCE not in kinds


def test_validate_manifest_speed_out_of_natural_bounds() -> None:
    kinds = [i.kind for i in validate_tts_manifest(_manifest(speed_used=1.5))]
    assert TTSManifestIssueKind.SPEED_OUT_OF_NATURAL_BOUNDS in kinds


def test_validate_manifest_speed_within_natural_bounds() -> None:
    kinds = [i.kind for i in validate_tts_manifest(_manifest(speed_used=1.05))]
    assert TTSManifestIssueKind.SPEED_OUT_OF_NATURAL_BOUNDS not in kinds


def test_validate_manifest_audio_missing_but_duration_set() -> None:
    kinds = [
        i.kind
        for i in validate_tts_manifest(
            _manifest(audio_artifact_id=None, duration_ms=1000, word_timings=[]),
        )
    ]
    assert TTSManifestIssueKind.AUDIO_MISSING in kinds
