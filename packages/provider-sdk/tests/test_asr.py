"""ASR 端口/Fake/路由：Unconfigured 诚实、Fake 回放+热词、路由按语言/策略/热词择优回退。"""

from pathlib import Path

from asr_fixtures import recorded_transcripts

from videoforge_provider_sdk import (
    ASRProvider,
    ASRRequest,
    ASRRouter,
    ASRStatus,
    FakeASRProvider,
    FakeLanguageSegmenter,
    LanguageSpan,
    UnconfiguredASRProvider,
    UnconfiguredLanguageSegmenter,
)

_AUDIO = Path("/tmp/a.wav")


def _fake(name, langs, *, loc="local", hotwords=False):
    return FakeASRProvider(
        name=name,
        languages=langs,
        execution_location=loc,
        supports_hotwords=hotwords,
        transcripts=recorded_transcripts(),
    )


# —— 默认 Unconfigured：不静默假装 ——

def test_unconfigured_provider_is_honest() -> None:
    r = UnconfiguredASRProvider().transcribe(ASRRequest(audio_path=_AUDIO, language_hint="zh-CN"))
    assert r.status is ASRStatus.UNCONFIGURED
    assert r.transcript is None
    assert isinstance(UnconfiguredASRProvider(), ASRProvider)


# —— Fake：回放录制转录 + 语言选择 ——

def test_fake_returns_recorded_transcript_for_language() -> None:
    r = _fake("asr.local", ("zh-CN", "en-US")).transcribe(
        ASRRequest(audio_path=_AUDIO, language_hint="zh-CN")
    )
    assert r.ok
    assert r.transcript is not None
    assert r.transcript.language == "zh-CN"
    assert r.transcript.segments[0].words[0].text == "今天"


def test_fake_low_overall_confidence_needs_review() -> None:
    # zh fixture 含 confidence=0.6 的段 → 低于 review_floor 0.7 → NEEDS_REVIEW
    req = ASRRequest(audio_path=_AUDIO, language_hint="zh-CN")
    r = _fake("asr.local", ("zh-CN",)).transcribe(req)
    assert r.status is ASRStatus.NEEDS_REVIEW
    assert str(r.error_code) == "ASR_LOW_CONFIDENCE"
    assert r.ok  # 仍产出转录（需审核，非失败）


def test_fake_unsupported_language() -> None:
    req = ASRRequest(audio_path=_AUDIO, language_hint="ja-JP")
    r = _fake("asr.local", ("en-US",)).transcribe(req)
    assert r.status is ASRStatus.UNSUPPORTED_LANGUAGE
    assert r.transcript is None


def test_hotword_injection_boosts_matching_word_and_records() -> None:
    prov = _fake("asr.funasr", ("zh-CN",), hotwords=True)
    r = prov.transcribe(ASRRequest(audio_path=_AUDIO, language_hint="zh-CN", hotwords=("M5",)))
    assert r.transcript.hotwords == ["M5"]
    m5 = next(w for w in r.transcript.segments[0].words if w.text == "M5")
    assert m5.confidence >= 0.98  # 热词偏置提升匹配词置信度


def test_provider_without_hotword_support_does_not_boost_or_falsely_record() -> None:
    prov = _fake("asr.plain", ("zh-CN",), hotwords=False)
    r = prov.transcribe(ASRRequest(audio_path=_AUDIO, language_hint="zh-CN", hotwords=("M5",)))
    m5 = next(w for w in r.transcript.segments[0].words if w.text == "M5")
    assert m5.confidence == 0.5  # 不支持热词 → 不改置信度
    assert r.transcript.hotwords == []  # 也不虚报注入了热词（诚实）


def test_declared_language_without_fixture_fails_not_wrong_language() -> None:
    # 声明支持 fr-FR 但只录了 zh/en → 请求 fr-FR 诚实 FAILED，不回放别的语言冒充
    prov = FakeASRProvider(
        name="asr.x", languages=("zh-CN", "fr-FR"),
        transcripts=recorded_transcripts(),  # 只有 zh-CN/en-US
    )
    r = prov.transcribe(ASRRequest(audio_path=_AUDIO, language_hint="fr-FR"))
    assert r.status is ASRStatus.FAILED
    assert r.transcript is None


# —— 路由：语言 + 策略 + 热词 ——

def test_router_prefers_local_then_falls_back_to_cloud() -> None:
    local = _fake("asr.whisper_cpp", ("zh-CN", "en-US"), loc="local")
    cloud = _fake("asr.whisperx", ("zh-CN", "en-US"), loc="cloud")
    router = ASRRouter([cloud, local])  # 乱序注册
    out = router.transcribe(ASRRequest(audio_path=_AUDIO, language_hint="en-US"))
    assert out.ok
    assert out.attempts[0].provider == "asr.whisper_cpp"  # local 优先（默认 local_preferred）


def test_router_cloud_preferred_policy() -> None:
    local = _fake("asr.whisper_cpp", ("en-US",), loc="local")
    cloud = _fake("asr.whisperx", ("en-US",), loc="cloud")
    out = ASRRouter([local, cloud]).transcribe(
        ASRRequest(audio_path=_AUDIO, language_hint="en-US", policy="cloud_preferred")
    )
    assert out.attempts[0].provider == "asr.whisperx"  # 云优先


def test_router_hotwords_prefer_hotword_capable_provider() -> None:
    plain = _fake("asr.whisper_cpp", ("zh-CN",), loc="local", hotwords=False)
    funasr = _fake("asr.funasr", ("zh-CN",), loc="cloud", hotwords=True)
    out = ASRRouter([plain, funasr]).transcribe(
        ASRRequest(audio_path=_AUDIO, language_hint="zh-CN", hotwords=("M5",))
    )
    assert out.attempts[0].provider == "asr.funasr"  # 需热词 → 支持热词的排前（即便是云）


def test_router_falls_back_over_unconfigured() -> None:
    unconf = UnconfiguredASRProvider("asr.local_unconf", languages=("zh-CN",))
    fake = _fake("asr.cloud", ("zh-CN",), loc="cloud")
    out = ASRRouter([unconf, fake]).transcribe(ASRRequest(audio_path=_AUDIO, language_hint="zh-CN"))
    assert out.ok
    assert [a.provider for a in out.attempts] == ["asr.local_unconf", "asr.cloud"]  # 回退


def test_router_all_unconfigured_returns_unconfigured() -> None:
    out = ASRRouter(
        [UnconfiguredASRProvider("a", languages=("zh-CN",)),
         UnconfiguredASRProvider("b", languages=("zh-CN",))]
    ).transcribe(ASRRequest(audio_path=_AUDIO, language_hint="zh-CN"))
    assert out.result.status is ASRStatus.UNCONFIGURED
    assert not out.ok


# —— 混语预分段端口 ——

def test_language_segmenter_fake_and_unconfigured() -> None:
    spans = [LanguageSpan(0, 1600, "zh-CN"), LanguageSpan(1600, 3000, "en-US")]
    assert FakeLanguageSegmenter(spans).segment(_AUDIO) == spans
    assert UnconfiguredLanguageSegmenter().segment(_AUDIO) == []  # 未接入 → 空（单语言+人工回退）
