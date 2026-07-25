"""VLM 端口/Fake：Unconfigured 诚实、批量一次调用（禁逐帧）、回填隔离、端到端选帧→分析。"""

import json
from datetime import UTC, datetime
from pathlib import Path

from videoforge_domain import select_representative_frames
from videoforge_provider_sdk import (
    FakeVLMProvider,
    UnconfiguredVLMProvider,
    VLMProvider,
    VLMRequest,
    VLMStatus,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "vlm" / "captions.json"
_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _captions() -> dict[int, tuple[str, list[str], float]]:
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return {int(k): (v["caption"], v["labels"], v["confidence"]) for k, v in raw.items()}


def _analysis(**over):
    kwargs = dict(
        analysis_id="va-1",
        created_at=_T0,
        duration_ms=30000,
        scene_cuts=(3.0, 10.0),
        periodic_interval_ms=999999,
    )
    kwargs.update(over)
    return select_representative_frames(**kwargs)


def test_unconfigured_is_honest() -> None:
    r = UnconfiguredVLMProvider().analyze(VLMRequest(analysis=_analysis()))
    assert r.status is VLMStatus.UNCONFIGURED
    assert r.analysis is None
    assert isinstance(UnconfiguredVLMProvider(), VLMProvider)


def test_batch_single_call_never_per_frame() -> None:
    va = _analysis()
    assert len(va.frames) >= 3  # 选了多帧
    prov = FakeVLMProvider(name="vlm.fake", captions=_captions())
    r = prov.analyze(VLMRequest(analysis=va))
    assert r.ok
    assert prov.call_count == 1  # 整批一次调用——绝不逐帧


def test_fills_captions_and_records_provider() -> None:
    prov = FakeVLMProvider(name="vlm.fake", captions=_captions(), version="v0")
    r = prov.analyze(VLMRequest(analysis=_analysis()))
    assert r.analysis.vlm_provider == "vlm.fake"
    assert r.analysis.vlm_version == "v0"
    f0 = next(f for f in r.analysis.frames if f.frame_time_ms == 0)
    assert f0.caption == "创作者出镜，桌面有芯片开发板"
    assert "person" in f0.labels


def test_frame_without_caption_stays_none() -> None:
    # 只录了 0/3000/10000；若选出别的帧则 caption 保持 None（诚实，不编造）
    prov = FakeVLMProvider(name="vlm.fake", captions={0: ("只有这帧", ["x"], 0.9)})
    r = prov.analyze(VLMRequest(analysis=_analysis()))
    uncaptioned = [f for f in r.analysis.frames if f.frame_time_ms != 0]
    assert all(f.caption is None for f in uncaptioned)


def test_analyze_does_not_mutate_request_or_leak() -> None:
    va = _analysis()
    before = va.model_dump()
    prov = FakeVLMProvider(name="vlm.fake", captions=_captions())
    r = prov.analyze(VLMRequest(analysis=va))
    # 改返回结果不应回污染入参
    r.analysis.frames[0].caption = "MUTATED"
    r.analysis.frames[0].labels.append("MUTATED")
    assert va.model_dump() == before  # 入参未被改动
    assert va.frames[0].caption is None
