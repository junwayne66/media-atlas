"""VF-404 provider-sdk TTS: Fake / Unconfigured / Router 测试。"""

from datetime import UTC, datetime

import pytest

from videoforge_contracts import (
    TTSProviderTier,
    VoiceKind,
    VoiceLicenseStatus,
    VoiceProfile,
    VoiceStyle,
)
from videoforge_provider_sdk import (
    FakeTTSProvider,
    TTSErrorCode,
    TTSProvider,
    TTSRequest,
    TTSRouter,
    TTSStatus,
    UnconfiguredTTSProvider,
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


def _req(
    text: str = "你好 世界",
    language: str = "zh-CN",
    voice: VoiceProfile | None = None,
    style: VoiceStyle | None = None,
    target: int | None = None,
    seed: int | None = None,
) -> TTSRequest:
    return TTSRequest(
        sentence_id="s0",
        text=text,
        language=language,
        voice_profile=voice or _profile(),
        style=style,
        target_duration_ms=target,
        seed=seed,
    )


# —— Protocol conformance ——


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeTTSProvider(), TTSProvider)


def test_unconfigured_satisfies_protocol() -> None:
    assert isinstance(UnconfiguredTTSProvider(), TTSProvider)


# —— Unconfigured 诚实 ——


def test_unconfigured_never_synthesizes() -> None:
    r = UnconfiguredTTSProvider().synthesize(_req())
    assert r.status is TTSStatus.UNCONFIGURED
    assert r.manifest is None
    assert r.error_code is TTSErrorCode.ENGINE_UNAVAILABLE


# —— VOICE_UNAUTHORIZED 硬红线（§7）——


@pytest.mark.parametrize(
    "bad_status",
    [
        VoiceLicenseStatus.PENDING,
        VoiceLicenseStatus.DENIED,
        VoiceLicenseStatus.UNCONFIRMED,
        VoiceLicenseStatus.EXPIRED,
    ],
)
def test_fake_rejects_non_authorized_voice(bad_status: VoiceLicenseStatus) -> None:
    r = FakeTTSProvider().synthesize(_req(voice=_profile(license_status=bad_status)))
    assert r.status is TTSStatus.VOICE_UNAUTHORIZED
    assert r.error_code is TTSErrorCode.VOICE_UNAUTHORIZED
    assert r.manifest is None


# —— Fake 合成语音 ——


def test_fake_synthesizes_zh_by_chars() -> None:
    r = FakeTTSProvider().synthesize(_req(text="你好世界", language="zh-CN"))
    assert r.status is TTSStatus.OK and r.manifest is not None
    assert r.manifest.duration_ms == 800  # 4 chars / 5.0 * 1000
    assert [w.text for w in r.manifest.word_timings] == ["你", "好", "世", "界"]
    assert r.manifest.audio_artifact_id is not None
    assert all(w.confidence == 0.5 for w in r.manifest.word_timings)


def test_fake_synthesizes_en_by_words() -> None:
    r = FakeTTSProvider().synthesize(_req(text="hello world", language="en-US"))
    assert r.status is TTSStatus.OK and r.manifest is not None
    assert r.manifest.duration_ms == 800  # 2 words / 2.5 * 1000
    assert [w.text for w in r.manifest.word_timings] == ["hello", "world"]


def test_fake_word_timings_monotonic_and_cover_full_duration() -> None:
    r = FakeTTSProvider().synthesize(_req(text="a b c d e", language="en-US"))
    assert r.manifest is not None
    words = r.manifest.word_timings
    assert words[0].start_ms == 0
    assert words[-1].end_ms == r.manifest.duration_ms
    for a, b in zip(words, words[1:], strict=False):
        assert a.end_ms == b.start_ms


def test_fake_pace_speeds_up_duration() -> None:
    """pace=1.5 应产更短音频。"""
    r_normal = FakeTTSProvider().synthesize(_req(text="你好世界"))
    r_fast = FakeTTSProvider().synthesize(
        _req(
            text="你好世界",
            style=VoiceStyle(pace=2.0),
        )
    )
    assert r_normal.manifest.duration_ms > r_fast.manifest.duration_ms


def test_fake_text_hash_matches_domain() -> None:
    """provider 内联 hash 与 domain.text_hash_of 应逐位一致。"""
    from videoforge_domain import text_hash_of

    req = _req(text="hi", language="en-US", seed=42)
    r = FakeTTSProvider().synthesize(req)
    assert r.manifest is not None
    expected = text_hash_of("hi", language="en-US", voice_profile_id="v1", seed=42)
    assert r.manifest.text_hash == expected


def test_fake_unsupported_language() -> None:
    p = FakeTTSProvider(supported_languages=("zh-CN",))
    r = p.synthesize(_req(text="hi", language="en-US"))
    assert r.status is TTSStatus.UNSUPPORTED_LANGUAGE
    assert r.error_code is TTSErrorCode.UNSUPPORTED_LANGUAGE


def test_fake_deep_copy_input() -> None:
    """修改 request 后再调用同 provider 不应受污染。"""
    p = FakeTTSProvider()
    req = _req(text="你好")
    r1 = p.synthesize(req)
    # frozen dataclass 无法直接改；此处验证 result.manifest 修改不污染 provider
    r1.manifest.word_timings.clear() if r1.manifest else None
    r2 = p.synthesize(_req(text="你好"))
    assert len(r2.manifest.word_timings) == 2


# —— TTSRouter ——


def _router(providers: dict[TTSProviderTier, TTSProvider]) -> TTSRouter:
    return TTSRouter(providers=providers)


def test_router_uses_first_tier_when_available() -> None:
    hq = FakeTTSProvider(name="hq", tier=TTSProviderTier.CLOUD_HIGH_QUALITY)
    sh = FakeTTSProvider(name="sh", tier=TTSProviderTier.SELF_HOSTED)
    r = _router(
        {
            TTSProviderTier.CLOUD_HIGH_QUALITY: hq,
            TTSProviderTier.SELF_HOSTED: sh,
        }
    ).synthesize(_req())
    assert r.status is TTSStatus.OK
    assert r.manifest.provider == "hq"


def test_router_fallback_on_unconfigured() -> None:
    hq = UnconfiguredTTSProvider(name="hq-unconf", tier=TTSProviderTier.CLOUD_HIGH_QUALITY)
    sh = FakeTTSProvider(name="sh", tier=TTSProviderTier.SELF_HOSTED)
    r = _router(
        {
            TTSProviderTier.CLOUD_HIGH_QUALITY: hq,
            TTSProviderTier.SELF_HOSTED: sh,
        }
    ).synthesize(_req())
    assert r.status is TTSStatus.OK
    assert r.manifest.provider == "sh"
    assert any("router attempts" in w for w in r.warnings)


def test_router_voice_unauthorized_is_terminal_no_fallback() -> None:
    """§7：VOICE_UNAUTHORIZED 不能被 fallback 到下一 tier 掩盖。"""
    hq = FakeTTSProvider(name="hq", tier=TTSProviderTier.CLOUD_HIGH_QUALITY)
    sh = FakeTTSProvider(name="sh", tier=TTSProviderTier.SELF_HOSTED)
    bad_voice = _profile(license_status=VoiceLicenseStatus.DENIED)
    r = _router(
        {
            TTSProviderTier.CLOUD_HIGH_QUALITY: hq,
            TTSProviderTier.SELF_HOSTED: sh,
        }
    ).synthesize(_req(voice=bad_voice))
    assert r.status is TTSStatus.VOICE_UNAUTHORIZED
    assert r.manifest is None


def test_router_unsupported_language_is_terminal_no_fallback() -> None:
    """品牌一致性：某 tier 不支持语言 = 终局；不应"降级"到别的 tier 完成合成——
    真正的 fallback 是给上层报错让人换配置。"""
    hq = FakeTTSProvider(name="hq", supported_languages=("zh-CN",))
    sh = FakeTTSProvider(name="sh", supported_languages=("en-US",))
    r = _router(
        {
            TTSProviderTier.CLOUD_HIGH_QUALITY: hq,
            TTSProviderTier.SELF_HOSTED: sh,
        }
    ).synthesize(_req(language="en-US"))
    assert r.status is TTSStatus.UNSUPPORTED_LANGUAGE


def test_router_all_failed_returns_failed() -> None:
    hq = UnconfiguredTTSProvider(name="hq-unc", tier=TTSProviderTier.CLOUD_HIGH_QUALITY)
    sh = UnconfiguredTTSProvider(name="sh-unc", tier=TTSProviderTier.SELF_HOSTED)
    r = _router(
        {
            TTSProviderTier.CLOUD_HIGH_QUALITY: hq,
            TTSProviderTier.SELF_HOSTED: sh,
        }
    ).synthesize(_req())
    assert r.status is TTSStatus.FAILED
