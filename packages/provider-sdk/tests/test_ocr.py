"""OCR 端口/Fake：Unconfigured 诚实、Fake 回放录制检测；端到端接域跟踪成 TextTrack。"""

import json
from pathlib import Path

from videoforge_contracts import TextObservation, TextTrackKind
from videoforge_domain import track_text_observations
from videoforge_provider_sdk import (
    FakeOCRProvider,
    OCRProvider,
    OCRRequest,
    OCRStatus,
    UnconfiguredOCRProvider,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ocr" / "observations.json"
_VIDEO = Path("/tmp/v.mp4")


def _recorded() -> list[TextObservation]:
    return [
        TextObservation.model_validate(o) for o in json.loads(_FIXTURE.read_text(encoding="utf-8"))
    ]


def test_unconfigured_is_honest() -> None:
    r = UnconfiguredOCRProvider().detect(OCRRequest(video_path=_VIDEO))
    assert r.status is OCRStatus.UNCONFIGURED
    assert r.observations == []
    assert isinstance(UnconfiguredOCRProvider(), OCRProvider)


def test_fake_replays_recorded_observations() -> None:
    prov = FakeOCRProvider(name="ocr.fake", observations=_recorded())
    r = prov.detect(OCRRequest(video_path=_VIDEO))
    assert r.ok
    assert len(r.observations) == 7
    assert isinstance(prov, OCRProvider)


def test_fake_does_not_leak_mutable_references() -> None:
    recorded = _recorded()
    prov = FakeOCRProvider(name="ocr.fake", observations=recorded)
    r = prov.detect(OCRRequest(video_path=_VIDEO))
    # 列表级 + 元素级 + 入参级 全部改动，都不应污染内部录制
    r.observations.clear()
    recorded[0].text = "MUTATED_INPUT"
    r2 = prov.detect(OCRRequest(video_path=_VIDEO))
    r2.observations[0].text = "MUTATED_RESULT"
    r2.observations[0].bbox.x = 0.0
    fresh = prov.detect(OCRRequest(video_path=_VIDEO))
    assert len(fresh.observations) == 7
    assert fresh.observations[0].text == "端侧推理很快"  # 未被入参/结果的改动污染
    assert fresh.observations[0].bbox.x != 0.0


def test_end_to_end_ocr_then_tracking() -> None:
    # OCR 原始检测 → 域跟踪 → 稳定 TextTrack（字幕投票纠错 + 水印分类）
    prov = FakeOCRProvider(name="ocr.fake", observations=_recorded())
    result = prov.detect(OCRRequest(video_path=_VIDEO))
    tracks = track_text_observations(result.observations, total_duration_ms=58000)

    assert len(tracks) == 2
    caption = next(t for t in tracks if t.kind is TextTrackKind.CAPTION)
    brand = next(t for t in tracks if t.kind is TextTrackKind.BRAND_MARK)
    assert caption.text == "端侧推理很快"  # 多帧投票纠正了误识帧
    assert len(caption.observations) == 4
    assert brand.text == "@创作者"
