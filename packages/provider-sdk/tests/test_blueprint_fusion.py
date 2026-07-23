"""Blueprint 融合端口/Fake：Unconfigured 诚实、端到端（转录+视觉→候选→融合→通过校验）。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    FrameAnalysis,
    FrameSampleReason,
    RhetoricalBeatKind,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
    VisualAnalysis,
)
from videoforge_domain import (
    build_candidate_rhetorical_beats,
    build_visual_beats,
    validate_blueprint,
)
from videoforge_provider_sdk import (
    BlueprintFusionProvider,
    BlueprintFusionRequest,
    BlueprintFusionStatus,
    FakeBlueprintFusionProvider,
    UnconfiguredBlueprintFusionProvider,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)
_DURATION = 12000


def _transcript() -> Transcript:
    return Transcript(
        id="tr", source_artifact_id="art-1", language="zh-CN",
        segments=[
            TranscriptSegment(id="seg-0", start_ms=0, end_ms=3000, speaker_id="spk_0",
                              language="zh-CN", text="今天拆解这款芯片", confidence=0.9),
            TranscriptSegment(id="seg-1", start_ms=4000, end_ms=9000, speaker_id="spk_0",
                              language="zh-CN", text="跑分是上代两倍", confidence=0.9),
        ],
        models=TranscriptModels(asr_provider="asr.x"), created_at=_T0,
    )


def _visual_analysis() -> VisualAnalysis:
    return VisualAnalysis(
        id="va", sampling_policy="representative@v1",
        frames=[
            FrameAnalysis(frame_time_ms=0, reasons=[FrameSampleReason.KEYFRAME], labels=["person"]),
            FrameAnalysis(frame_time_ms=4000, reasons=[FrameSampleReason.SCENE_CUT],
                          labels=["screen_record"]),
        ],
        created_at=_T0,
    )


def _request() -> BlueprintFusionRequest:
    tr = _transcript()
    return BlueprintFusionRequest(
        blueprint_id="bp-1", created_at=_T0, duration_ms=_DURATION,
        candidate_beats=build_candidate_rhetorical_beats(tr, _DURATION),
        visual_beats=build_visual_beats(_visual_analysis(), _DURATION),
        transcript=tr, source_artifact_id="art-1",
    )


def test_unconfigured_is_honest() -> None:
    r = UnconfiguredBlueprintFusionProvider().fuse(_request())
    assert r.status is BlueprintFusionStatus.UNCONFIGURED
    assert r.blueprint is None
    assert isinstance(UnconfiguredBlueprintFusionProvider(), BlueprintFusionProvider)


def test_fake_fusion_produces_valid_blueprint() -> None:
    # 端到端：ASR+OCR+VLM → 域候选 → 融合 → 通过校验护栏（零 issue）
    r = FakeBlueprintFusionProvider().fuse(_request())
    assert r.ok
    bp = r.blueprint
    assert bp is not None
    issues = validate_blueprint(
        bp, transcript_segment_ids={"seg-0", "seg-1"}, text_track_ids=set()
    )
    assert issues == [], issues  # 合法蓝图：时间在时长内、单调、证据引用真实、覆盖率达标


def test_fake_assigns_hook_and_cta_keeps_middle_unclassified() -> None:
    bp = FakeBlueprintFusionProvider().fuse(_request()).blueprint
    assert bp.rhetorical_beats[0].kind is RhetoricalBeatKind.HOOK
    assert bp.rhetorical_beats[-1].kind is RhetoricalBeatKind.CTA
    # 诚实：Fake 不假装分类中间节拍
    assert any(b.kind is RhetoricalBeatKind.UNCLASSIFIED for b in bp.rhetorical_beats[1:-1])


def test_fake_claim_cites_real_transcript_segment() -> None:
    bp = FakeBlueprintFusionProvider().fuse(_request()).blueprint
    assert len(bp.claims) == 1
    ev = bp.claims[0].evidence[0]
    assert ev.kind == "transcript" and ev.ref_id == "seg-0"  # 引用真实段
    # claim 挂在覆盖 seg-0 起点的节拍上
    assert "claim-0" in [cid for b in bp.rhetorical_beats for cid in b.claim_ids]


def test_fake_does_not_fabricate_timestamps() -> None:
    # 融合结果的节拍时间戳必须来自候选（程序提供），Fake 不越界
    req = _request()
    cand_bounds = {(b.start_ms, b.end_ms) for b in req.candidate_beats}
    bp = FakeBlueprintFusionProvider().fuse(req).blueprint
    for b in bp.rhetorical_beats:
        assert (b.start_ms, b.end_ms) in cand_bounds  # 只改 kind，不动时间


def test_fake_does_not_mutate_request_candidates() -> None:
    req = _request()
    before = [b.model_dump() for b in req.candidate_beats]
    FakeBlueprintFusionProvider().fuse(req)
    assert [b.model_dump() for b in req.candidate_beats] == before  # 候选未被改动
