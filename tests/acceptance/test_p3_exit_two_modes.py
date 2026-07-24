"""P3 Exit 验收 —— 20 中英样本两模式共 Blueprint 端到端 Package 产出（§12）。

覆盖：STRUCTURE_REWRITE + SOURCE_REEDIT 从同一 Blueprint 生成独立 Package，
每 Package = Script + Highlight + AssetPlan + CreativeTimeline + QA。所有 domain
guardrails（validate_script/validate_asset_plan/validate_timeline/publish_gate）必须过。
"""

from __future__ import annotations

from datetime import UTC, datetime

from p3_samples import SAMPLES

from videoforge_contracts import (
    AssetLicense,
    AssetLicenseType,
    AssetPlanSlot,
    AssetRole,
    AssetSource,
    CompositionSpec,
    CreationMode,
    CreativeOpportunity,
    CreativeTimeline,
    HighlightWeights,
    QAFindingKind,
    QASeverity,
    RationalTime,
    RationalTimeRange,
    Segment,
    Track,
    TrackKind,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
)
from videoforge_domain import (
    AssetCandidate,
    AudioWindowSample,
    CaptionBoundingBox,
    MediaSampleInput,
    PublishGate,
    VideoFrameSample,
    aggregate_qa_report,
    build_beat_template,
    build_candidate_windows,
    build_claim_table,
    build_creative_brief,
    is_valid_asset_plan,
    is_valid_script,
    is_valid_timeline,
    rank_highlights,
    resolve_asset_plan,
    validate_publish_gate,
)
from videoforge_provider_sdk import (
    FakeHighlightFeatureProvider,
    FakeStructureRewriteProvider,
    HighlightFeatureRequest,
    HighlightWindowSpec,
    RewriteRequest,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)
_WEIGHTS = HighlightWeights(template_version="p3-exit-v1")


def _fake_transcript(sample_id: str, language: str, duration_ms: int) -> Transcript:
    """构造 6 句均匀分布的转录（供 Highlight/Reedit 消费）。"""
    seg_dur = duration_ms // 6
    segs = [
        TranscriptSegment(
            id=f"{sample_id}-seg-{i}", start_ms=i * seg_dur, end_ms=(i + 1) * seg_dur,
            language=language, text=f"第{i}句 sample={sample_id} content", confidence=0.9,
        )
        for i in range(6)
    ]
    return Transcript(
        id=f"tr-{sample_id}", language=language, duration_ms=duration_ms,
        segments=segs, models=TranscriptModels(asr_provider="fake"), created_at=_T0,
    )


def _build_structure_rewrite(sample) -> dict:
    """STRUCTURE_REWRITE 模式：Blueprint → ClaimTable → Brief → BeatTemplate → Script。"""
    opp = CreativeOpportunity(
        id=f"opp-{sample.id}", blueprint_id=sample.blueprint.id,
        rationale="p3 exit sample", target_platform="douyin",
        target_language=sample.language, created_at=_T0,
    )
    table = build_claim_table(sample.blueprint, table_id=f"ct-{sample.id}", created_at=_T0)
    # 只选 usable 的 claim 作 must_cover（DISPUTED 不入）
    usable_ids = tuple(e.claim_id for e in table.entries if e.usable_in_rewrite)
    brief = build_creative_brief(
        opp, brief_id=f"b-{sample.id}", created_at=_T0, objective="verify",
        audience="acceptance", angle="p3 exit",
        duration_target_ms=sample.duration_target_ms,
        creation_mode=CreationMode.STRUCTURE_REWRITE, claim_table=table,
        must_cover_claim_ids=usable_ids,
    )
    template = build_beat_template(
        sample.blueprint, template_id=f"tpl-{sample.id}", created_at=_T0,
        duration_target_ms=sample.duration_target_ms,
    )
    rewrite_req = RewriteRequest(
        script_id=f"sc-{sample.id}", created_at=_T0, language=sample.language,
        beat_template=template, claim_table=table, brief=brief,
    )
    result = FakeStructureRewriteProvider().rewrite(rewrite_req)
    return {
        "brief": brief, "claim_table": table, "template": template,
        "script": result.script, "opp": opp,
    }


def _build_source_reedit(sample) -> dict:
    """SOURCE_REEDIT 模式：Blueprint → Transcript → Highlight 候选 + Top-N。"""
    tr = _fake_transcript(sample.id, sample.language, sample.blueprint.duration_ms)
    max_ms = min(60000, sample.blueprint.duration_ms)
    windows = build_candidate_windows(tr, min_ms=5000, max_ms=max_ms)
    specs = [
        HighlightWindowSpec(start_ms=w.start_ms, end_ms=w.end_ms, text=w.text,
                             index_in_video=i, total_windows=len(windows))
        for i, w in enumerate(windows)
    ]
    feats = FakeHighlightFeatureProvider().score(
        HighlightFeatureRequest(windows=specs, video_duration_ms=sample.blueprint.duration_ms)
    )
    hl = rank_highlights(
        windows, feats.features, weights=_WEIGHTS, top_n=3,
        id_prefix=f"hl-{sample.id}", created_at=_T0,
        source_transcript_id=tr.id, feature_provider="fake",
    )
    return {"transcript": tr, "highlight_set": hl, "windows": windows}


def _build_asset_plan_and_timeline(sample) -> tuple:
    """基础 AssetPlan + CreativeTimeline（两模式共用）。"""
    slot = AssetPlanSlot(
        slot_id="slot-0", start_ms=0, end_ms=min(5000, sample.duration_target_ms),
        role=AssetRole.B_ROLL, query="p3 exit b-roll",
        composition=CompositionSpec(aspect_ratio="9:16", safe_area="center"),
        allowed_sources=[AssetSource.OWN_LIBRARY, AssetSource.PLACEHOLDER],
        fallback=AssetRole.INFO_CARD,
    )
    cand = AssetCandidate(
        asset_id=f"lib-{sample.id}", source=AssetSource.OWN_LIBRARY,
        license=AssetLicense(type=AssetLicenseType.OWNED, holder="videoforge"),
        query="p3 exit b-roll", semantic=0.8, composition=0.7, resolution=0.7,
        motion=0.5, color=0.5, brand_ok=1.0,
    )
    plan = resolve_asset_plan(
        [slot], {AssetSource.OWN_LIBRARY: [cand]},
        plan_id=f"ap-{sample.id}", created_at=_T0,
    )

    rate = 30
    def rt(v: int) -> RationalTime:
        return RationalTime(value=v, rate=rate)
    dur_frames = int(round(sample.duration_target_ms / 1000 * rate))
    v1 = Track(id="v1", kind=TrackKind.V1_PRIMARY_VIDEO, segments=[
        Segment(id="v1-s0", time_range=RationalTimeRange(start=rt(0), duration=rt(dur_frames)),
                 source_ref=f"art-{sample.blueprint.id}", semantic_role="HOOK"),
    ])
    a0 = Track(id="a0", kind=TrackKind.A0_ORIGINAL, segments=[
        Segment(id="a0-s0", time_range=RationalTimeRange(start=rt(0), duration=rt(dur_frames))),
    ])
    timeline = CreativeTimeline(
        id=f"tl-{sample.id}", rate=rate, duration=rt(dur_frames),
        tracks=[v1, a0], created_at=_T0,
    )
    return plan, timeline


def _run_qa(timeline: CreativeTimeline) -> tuple:
    """跑 QA 规则 → 应零 BLOCKER（clean 合成媒体输入触发规则真正执行）。

    verifier 指出 `video_frames=[]` + `captions=[]` 使黑帧/冻结帧/字幕规则**结构上不可能触发**
    ——只证了"空输入过门"。此处注入**每 500ms 一帧**（亮度充分、phash 递增避免重复）+
    **合规字幕框**（居中安全区内），使所有 9 条规则真正跑起来，clean 结果下应产 0 BLOCKER。
    """
    tl_ms = int(timeline.duration.value / timeline.duration.rate * 1000)
    # 每 500ms 一个视频帧：亮度 = 128（远高于黑帧阈值），phash 递增（无重复/冻结）
    video_frames = [
        VideoFrameSample(at_ms=t, mean_luma=128.0,
                          phash=f"{i:016x}0000000000000000")
        for i, t in enumerate(range(0, tl_ms, 500))
    ]
    # 一个 3s 字幕，居中安全区内（left=20/right=80/top=80/bottom=95，均在 5-95 内、不重叠）
    captions = [
        CaptionBoundingBox(caption_id="cap-0", at_ms=1000, duration_ms=3000,
                             left_pct=20.0, top_pct=80.0,
                             right_pct=80.0, bottom_pct=95.0),
    ]
    input_data = MediaSampleInput(
        video_frames=video_frames,
        audio_windows=[AudioWindowSample(
            at_ms=0, duration_ms=tl_ms,
            lufs=-14.0, true_peak_dbtp=-3.0, has_voice=False, tail_amplitude=0.001,
        )],
        captions=captions,
        broll_duration_ms=tl_ms,  # broll ratio = 1.0 ≥ 0.15
        total_video_duration_ms=tl_ms,
        measured_duration_ms=tl_ms,  # 与 timeline 匹配 → 无 duration 差
    )
    report = aggregate_qa_report(
        input_data, report_id=f"qa-{timeline.id}", timeline_id=timeline.id,
        timeline_duration_ms=tl_ms, created_at=_T0,
    )
    return report, validate_publish_gate(report.findings)


def test_all_samples_produce_both_mode_packages() -> None:
    """§12: 两种模式均可从同一 Blueprint 生成独立 Package，全部过 domain 护栏。"""
    assert len(SAMPLES) == 20
    for sample in SAMPLES:
        # STRUCTURE_REWRITE
        rewrite = _build_structure_rewrite(sample)
        assert rewrite["script"] is not None, f"{sample.id}: rewrite Fake 未产脚本"
        # 计入的 must_cover 与 usable 一致，脚本应过 validate_script
        assert is_valid_script(
            rewrite["script"], claim_table=rewrite["claim_table"], brief=rewrite["brief"],
        ), f"{sample.id}: STRUCTURE_REWRITE 脚本 validate_script 未过"

        # SOURCE_REEDIT
        reedit = _build_source_reedit(sample)
        assert reedit["highlight_set"].candidates, f"{sample.id}: Highlight 无候选"
        # Top-3 上限（可能少于 3 若样本短）
        assert 1 <= len(reedit["highlight_set"].candidates) <= 3

        # AssetPlan + CreativeTimeline 两模式共用
        plan, timeline = _build_asset_plan_and_timeline(sample)
        assert is_valid_asset_plan(plan), f"{sample.id}: asset plan validate 未过"
        assert is_valid_timeline(timeline), f"{sample.id}: timeline validate 未过"

        # QA 发布门
        report, gate = _run_qa(timeline)
        assert gate is PublishGate.PASS, f"{sample.id}: QA 发布门未过 findings={report.findings}"


def test_no_unexpected_blocker_across_all_samples() -> None:
    """§12: 20 样本无非预期黑帧/空轨/音频尾切 —— clean fixture 输入下不得产 BLOCKER。"""
    blocker_findings: dict[str, list] = {}
    for sample in SAMPLES:
        _plan, timeline = _build_asset_plan_and_timeline(sample)
        report, _gate = _run_qa(timeline)
        blockers = [f for f in report.findings if f.severity is QASeverity.BLOCKER]
        if blockers:
            blocker_findings[sample.id] = [f.kind.value for f in blockers]
    assert not blocker_findings, (
        f"{len(blocker_findings)}/20 样本有非预期 BLOCKER: {blocker_findings}"
    )
    # 确保 QAFindingKind 枚举被引用（导入验证）
    assert QAFindingKind.BLACK_FRAME.value == "BLACK_FRAME"


def test_disputed_claims_never_forced_into_scripts() -> None:
    """STRUCTURE_REWRITE 安全属性：DISPUTED 事实即便 must_cover 强含也绝不被脚本引用。

    verifier REFUTED 之前的 vacuous 版本：`_build_structure_rewrite` 事先把 DISPUTED
    从 usable 过滤掉再传 must_cover，断言"cited 无 DISPUTED"永远成立（因为 must_cover
    本就无 DISPUTED）。这里**直接构造 must_cover 强含 DISPUTED 的 brief**，直调 Fake，
    观察 script 是否真的避开 DISPUTED。这是安全属性的真实证明。
    """
    from videoforge_contracts import ClaimSourceStatus
    disputed_samples = [
        s for s in SAMPLES
        if any(c.source_status is ClaimSourceStatus.DISPUTED for c in s.blueprint.claims)
    ]
    assert disputed_samples, "验收样本应含 DISPUTED claim 覆盖"
    for sample in disputed_samples:
        opp = CreativeOpportunity(
            id=f"opp-{sample.id}", blueprint_id=sample.blueprint.id,
            rationale="disputed probe", target_platform="douyin",
            target_language=sample.language, created_at=_T0,
        )
        table = build_claim_table(sample.blueprint,
                                     table_id=f"ct-{sample.id}", created_at=_T0)
        # 关键：**故意**把 DISPUTED claim 塞进 must_cover（生产不会做，但 Fake 契约必须扛）
        disputed_ids = tuple(
            c.id for c in sample.blueprint.claims
            if c.source_status is ClaimSourceStatus.DISPUTED
        )
        assert disputed_ids
        brief = build_creative_brief(
            opp, brief_id=f"b-{sample.id}", created_at=_T0, objective="verify",
            audience="acceptance", angle="disputed probe",
            duration_target_ms=sample.duration_target_ms,
            creation_mode=CreationMode.STRUCTURE_REWRITE, claim_table=table,
            must_cover_claim_ids=disputed_ids,
        )
        template = build_beat_template(
            sample.blueprint, template_id=f"tpl-{sample.id}", created_at=_T0,
            duration_target_ms=sample.duration_target_ms,
        )
        result = FakeStructureRewriteProvider().rewrite(RewriteRequest(
            script_id=f"sc-{sample.id}", created_at=_T0, language=sample.language,
            beat_template=template, claim_table=table, brief=brief,
        ))
        assert result.script is not None, f"{sample.id}: Fake 未产脚本"
        cited = {cid for s in result.script.sentences for cid in s.claim_ids}
        assert not (cited & set(disputed_ids)), \
            f"{sample.id}: Fake 引用了 DISPUTED cited={cited & set(disputed_ids)}"
