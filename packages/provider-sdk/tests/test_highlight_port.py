"""热门片段特征端口：Unconfigured 诚实 + Fake 确定性/对齐 + 端到端过纯域排序。

端到端（provider-sdk 测试可依赖 domain 做验收，同 blueprint_fusion/vlm/ocr 先例）：
Transcript → build_candidate_windows → HighlightWindowSpec → Fake.score → rank_highlights → Top-N。
"""

from datetime import UTC, datetime

from videoforge_contracts import (
    HighlightWeights,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
)
from videoforge_domain import (
    CandidateWindow,
    build_candidate_windows,
    overlap_ratio,
    rank_highlights,
)
from videoforge_provider_sdk import (
    FakeHighlightFeatureProvider,
    HighlightFeatureProvider,
    HighlightFeatureRequest,
    HighlightFeatureStatus,
    HighlightWindowSpec,
    UnconfiguredHighlightFeatureProvider,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)
_WEIGHTS = HighlightWeights(template_version="highlight-v1")


def _transcript(n: int, seg_ms: int = 5000) -> Transcript:
    return Transcript(
        id="tr",
        language="zh-CN",
        segments=[
            TranscriptSegment(
                id=f"seg-{i}",
                start_ms=i * seg_ms,
                end_ms=(i + 1) * seg_ms,
                language="zh-CN",
                text=f"第{i}句讲了一个要点并给出实测结论",
                confidence=0.9,
            )
            for i in range(n)
        ],
        models=TranscriptModels(asr_provider="asr.x"),
        created_at=_T0,
    )


def _spec(start: int, end: int, text: str, idx: int, total: int) -> HighlightWindowSpec:
    return HighlightWindowSpec(
        start_ms=start, end_ms=end, text=text, index_in_video=idx, total_windows=total
    )


def test_protocol_conformance() -> None:
    assert isinstance(FakeHighlightFeatureProvider(), HighlightFeatureProvider)
    assert isinstance(UnconfiguredHighlightFeatureProvider(), HighlightFeatureProvider)


def test_unconfigured_is_honest() -> None:
    prov = UnconfiguredHighlightFeatureProvider()
    req = HighlightFeatureRequest(windows=[_spec(0, 20000, "x", 0, 1)])
    result = prov.score(req)
    assert result.status is HighlightFeatureStatus.UNCONFIGURED
    assert result.features == []  # 绝不静默造特征
    assert result.error_code is not None
    assert prov.health_check().status is HighlightFeatureStatus.UNCONFIGURED


def test_fake_deterministic_and_aligned() -> None:
    specs = [_spec(i * 5000, i * 5000 + 20000, f"窗口{i}的文本内容", i, 4) for i in range(4)]
    req = HighlightFeatureRequest(windows=specs, video_duration_ms=40000)
    fake = FakeHighlightFeatureProvider()
    a = fake.score(req)
    b = fake.score(req)
    assert a.ok and len(a.features) == len(specs)  # 与窗口一一对齐
    assert [f.model_dump() for f in a.features] == [f.model_dump() for f in b.features]  # 可复现


def test_fake_position_signal_hook_vs_ending() -> None:
    # 靠前窗口 hook 更强、靠后窗口 ending_payoff 更强（位置信号确定性）
    specs = [_spec(i * 5000, i * 5000 + 20000, "同样的文本", i, 4) for i in range(4)]
    feats = (
        FakeHighlightFeatureProvider()
        .score(HighlightFeatureRequest(windows=specs, video_duration_ms=40000))
        .features
    )
    assert feats[0].hook_strength > feats[-1].hook_strength
    assert feats[-1].ending_payoff > feats[0].ending_payoff


def test_end_to_end_transcript_to_top_n() -> None:
    tr = _transcript(8)  # 8 句 × 5s = 40s
    windows = build_candidate_windows(tr, min_ms=12000, max_ms=30000)
    assert windows
    specs = [_spec(w.start_ms, w.end_ms, w.text, i, len(windows)) for i, w in enumerate(windows)]
    result_feats = FakeHighlightFeatureProvider().score(
        HighlightFeatureRequest(windows=specs, video_duration_ms=40000)
    )
    assert result_feats.ok

    hl = rank_highlights(
        windows,
        result_feats.features,
        weights=_WEIGHTS,
        top_n=3,
        id_prefix="01J2ZK3AC9V6XW8YQ4R5T6U7ZH",
        created_at=_T0,
        source_transcript_id=tr.id,
        feature_provider="highlight.fake",
    )
    assert 1 <= len(hl.candidates) <= 3
    assert hl.feature_provider == "highlight.fake"
    assert hl.weights_version == "highlight-v1"

    starts = {s.start_ms for s in tr.segments}
    ends = {s.end_ms for s in tr.segments}
    for c in hl.candidates:
        assert c.start_ms in starts and c.end_ms in ends  # 不切句
        assert 0 <= c.start_ms < c.end_ms <= 40000
        assert c.weights_version == "highlight-v1"
    # 首个是最高分
    assert hl.candidates[0].score == max(c.score for c in hl.candidates)
    # Top-N 之间不应高度重叠（去重生效）
    picked = [
        CandidateWindow(c.start_ms, c.end_ms, tuple(c.segment_ids), "") for c in hl.candidates
    ]
    for i in range(len(picked)):
        for j in range(i + 1, len(picked)):
            assert overlap_ratio(picked[i], picked[j]) <= 0.7
