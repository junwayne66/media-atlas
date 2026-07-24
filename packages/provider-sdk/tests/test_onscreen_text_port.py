"""VF-403 provider-sdk CleanPlate/TextRedraw 测试。"""

from videoforge_contracts import (
    CleanPlateMethod,
    CleanPlateRequest,
    TextLocalizationStrategy,
    TextTrackKind,
    TextTrackLocalizationDecision,
)
from videoforge_provider_sdk import (
    CleanPlateErrorCode,
    CleanPlateProvider,
    CleanPlateStatus,
    FakeCleanPlateProvider,
    FakeTextRedrawProvider,
    TextRedrawErrorCode,
    TextRedrawProvider,
    TextRedrawRequest,
    TextRedrawStatus,
    UnconfiguredCleanPlateProvider,
    UnconfiguredTextRedrawProvider,
)


def _cp_request(method: CleanPlateMethod = CleanPlateMethod.BACKGROUND_ESTIMATE,
                  license_ref: str | None = None) -> CleanPlateRequest:
    return CleanPlateRequest(
        id="cp-x", source_track_id="tt-0", source_artifact_id="art-0",
        frame_start_ms=0, frame_end_ms=1000, method=method, license_ref=license_ref,
    )


def _decision(strategy=TextLocalizationStrategy.REDRAW,
                translated="On-device 20 ms",
                source_text="端侧推理 20ms 完成") -> TextTrackLocalizationDecision:
    return TextTrackLocalizationDecision(
        source_track_id="tt-0", source_text=source_text,
        source_kind=TextTrackKind.CAPTION, target_language="en-US",
        strategy=strategy, translated_text=translated, rationale="test",
    )


# —— Protocol conformance ——

def test_fake_clean_plate_satisfies_protocol() -> None:
    assert isinstance(FakeCleanPlateProvider(), CleanPlateProvider)


def test_unconfigured_clean_plate_satisfies_protocol() -> None:
    assert isinstance(UnconfiguredCleanPlateProvider(), CleanPlateProvider)


def test_fake_text_redraw_satisfies_protocol() -> None:
    assert isinstance(FakeTextRedrawProvider(), TextRedrawProvider)


def test_unconfigured_text_redraw_satisfies_protocol() -> None:
    assert isinstance(UnconfiguredTextRedrawProvider(), TextRedrawProvider)


# —— Unconfigured ——

def test_unconfigured_clean_plate_never_produces() -> None:
    r = UnconfiguredCleanPlateProvider().generate(_cp_request())
    assert r.status is CleanPlateStatus.UNCONFIGURED
    assert r.clean_plate_artifact_id is None
    assert r.error_code is CleanPlateErrorCode.PIPELINE_UNAVAILABLE


def test_unconfigured_text_redraw_never_produces() -> None:
    r = UnconfiguredTextRedrawProvider().redraw(
        TextRedrawRequest(decision=_decision()),
    )
    assert r.status is TextRedrawStatus.UNCONFIGURED
    assert r.rendered_artifact_id is None
    assert r.error_code is TextRedrawErrorCode.RENDERER_UNAVAILABLE


# —— Fake Clean Plate ——

def test_fake_clean_plate_returns_dummy_artifact_id() -> None:
    r = FakeCleanPlateProvider().generate(_cp_request())
    assert r.status is CleanPlateStatus.OK
    assert r.clean_plate_artifact_id is not None
    assert "fake" in r.clean_plate_artifact_id
    assert r.warnings, "Fake 应带明示 warning 标示非真实产出"


def test_fake_clean_plate_skip_method_no_artifact() -> None:
    r = FakeCleanPlateProvider().generate(_cp_request(method=CleanPlateMethod.SKIP))
    assert r.status is CleanPlateStatus.OK
    assert r.clean_plate_artifact_id is None
    assert any("SKIP" in w for w in r.warnings)


def test_fake_clean_plate_deterministic_counter_per_instance() -> None:
    """counter 递增给不同 request 产不同 dummy id（同 instance）。"""
    p = FakeCleanPlateProvider()
    r1 = p.generate(_cp_request())
    r2 = p.generate(CleanPlateRequest(
        id="cp-y", source_track_id="tt-1", source_artifact_id="art-1",
        frame_start_ms=0, frame_end_ms=1000,
        method=CleanPlateMethod.BACKGROUND_ESTIMATE,
    ))
    assert r1.clean_plate_artifact_id != r2.clean_plate_artifact_id


# —— Fake Text Redraw ——

def test_fake_redraw_ok_when_ratio_within_bound() -> None:
    r = FakeTextRedrawProvider().redraw(TextRedrawRequest(
        decision=_decision(source_text="A" * 10, translated="X" * 12),
        clean_plate_artifact_id="cp-fake-1", max_expansion_ratio=1.3,
    ))
    assert r.status is TextRedrawStatus.OK
    assert r.rendered_artifact_id is not None
    assert r.expansion_ratio == 1.2


def test_fake_redraw_layout_overflow_reports() -> None:
    r = FakeTextRedrawProvider().redraw(TextRedrawRequest(
        decision=_decision(source_text="A" * 10, translated="X" * 20),
        clean_plate_artifact_id="cp-fake-1", max_expansion_ratio=1.3,
    ))
    assert r.status is TextRedrawStatus.LAYOUT_OVERFLOW
    assert r.rendered_artifact_id is None


def test_fake_redraw_missing_clean_plate_fails() -> None:
    r = FakeTextRedrawProvider().redraw(TextRedrawRequest(
        decision=_decision(), clean_plate_artifact_id=None,
    ))
    assert r.status is TextRedrawStatus.FAILED
    assert r.error_code is TextRedrawErrorCode.CLEAN_PLATE_MISSING


def test_fake_redraw_missing_translation_fails() -> None:
    """translated_text 空字符串被 pydantic 拒（min_length=1）；直接构造 None decision
    走 provider `decision.translated_text is None` 分支。"""
    from videoforge_contracts import TextTrackLocalizationDecision as D
    d = D(
        source_track_id="tt-0", source_text="src",
        source_kind=TextTrackKind.CAPTION, target_language="en-US",
        strategy=TextLocalizationStrategy.SKIP,
        translated_text=None, rationale="test",
    )
    r = FakeTextRedrawProvider().redraw(TextRedrawRequest(
        decision=d, clean_plate_artifact_id="cp",
    ))
    assert r.status is TextRedrawStatus.FAILED
