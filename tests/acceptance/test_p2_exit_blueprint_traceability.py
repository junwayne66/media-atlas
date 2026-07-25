"""P2 Exit 验收（Blueprint 可追溯）：20+ 中英样本走全链路，每个 Blueprint 可追溯到证据。

53 §P2 Exit：「20 条中英样本 Blueprint 可追溯到证据」。54 §2 Blueprint 行：已分析视频 →
融合 → Claim/Beat 都有证据时间点。用 Fake 把 ASR→OCR→VLM→Blueprint 串起来，逐条验证：
校验护栏零 issue、每 Claim 证据引用真实 transcript 段/文本轨、每节拍时间来自程序候选（未编造）。
"""

from datetime import UTC, datetime

from p2_samples import Sample, p2_samples

from videoforge_contracts import VideoBlueprint
from videoforge_domain import (
    build_candidate_rhetorical_beats,
    build_visual_beats,
    validate_blueprint,
)
from videoforge_provider_sdk import BlueprintFusionRequest, FakeBlueprintFusionProvider

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _blueprint(s: Sample) -> VideoBlueprint:
    candidates = build_candidate_rhetorical_beats(s.transcript, s.duration_ms)
    visual = build_visual_beats(s.visual_analysis, s.duration_ms)
    req = BlueprintFusionRequest(
        blueprint_id=s.id,
        created_at=_T0,
        duration_ms=s.duration_ms,
        candidate_beats=candidates,
        visual_beats=visual,
        transcript=s.transcript,
    )
    return FakeBlueprintFusionProvider().fuse(req).blueprint


def _seg_ids(s: Sample) -> set[str]:
    return {seg.id for seg in s.transcript.segments}


def _track_ids(s: Sample) -> set[str]:
    return {t.id for t in s.text_tracks}


def test_at_least_20_samples() -> None:
    assert len(p2_samples()) >= 20


def test_all_blueprints_pass_validation_guardrail() -> None:
    for s in p2_samples():
        bp = _blueprint(s)
        issues = validate_blueprint(
            bp, transcript_segment_ids=_seg_ids(s), text_track_ids=_track_ids(s)
        )
        assert issues == [], (s.id, issues)  # 零违规


def test_every_claim_traceable_to_real_evidence() -> None:
    for s in p2_samples():
        bp = _blueprint(s)
        seg_ids, track_ids = _seg_ids(s), _track_ids(s)
        assert bp.claims, s.id  # 至少产出一条 Claim
        for c in bp.claims:
            assert c.evidence, (s.id, c.id)  # Claim 必引证据
            for ev in c.evidence:
                valid = seg_ids if ev.kind == "transcript" else track_ids
                assert ev.ref_id in valid, (s.id, ev.ref_id)  # 可回跳到真实证据


def test_every_beat_time_comes_from_candidates() -> None:
    # 节拍时间戳来自程序候选（LLM/Fake 不编造），且在 [0,duration] 内
    for s in p2_samples():
        cands = {
            (b.start_ms, b.end_ms)
            for b in build_candidate_rhetorical_beats(s.transcript, s.duration_ms)
        }
        bp = _blueprint(s)
        for b in bp.rhetorical_beats:
            assert (b.start_ms, b.end_ms) in cands, (s.id, b.id)
            assert 0 <= b.start_ms <= b.end_ms <= s.duration_ms


def test_every_beat_claim_id_resolves() -> None:
    for s in p2_samples():
        bp = _blueprint(s)
        claim_ids = {c.id for c in bp.claims}
        for b in bp.rhetorical_beats:
            for cid in b.claim_ids:
                assert cid in claim_ids, (s.id, cid)


def test_language_coverage_zh_en_mixed() -> None:
    ids = {s.id.split("-")[0] for s in p2_samples()}
    assert {"zh", "en", "mix"} <= ids  # 覆盖中/英/混语
