"""VF-406 口型 domain 测试：§10.1 资格门 + §10.2 回退阶梯 + 非阻塞/自动降级红线。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    LipSyncEligibilityCriteria,
    LipSyncIneligibleReason,
    LipSyncMethod,
    LipSyncMode,
    LipSyncPlan,
    LipSyncQAReport,
    LipSyncReviewReason,
    LipSyncSegmentDecision,
)
from videoforge_domain import (
    LipSyncAvailability,
    LipSyncIssueKind,
    LipSyncSegmentFeatures,
    LipSyncSegmentInput,
    assess_eligibility,
    decide_lipsync,
    is_valid_lipsync_plan,
    plan_lipsync,
    resolve_fallback,
    validate_lipsync_plan,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)
_C = LipSyncEligibilityCriteria()


def _feat(**over) -> LipSyncSegmentFeatures:
    base = dict(
        face_count=1,
        face_height_ratio=0.3,
        occlusion_ratio=0.05,
        speaker_probability=0.9,
        head_turn_deg=10.0,
        duration_ms=3000,
        dub_aligned=True,
    )
    base.update(over)
    return LipSyncSegmentFeatures(**base)


def _qa(passed: bool) -> LipSyncQAReport:
    v = 0.9 if passed else 0.4
    return LipSyncQAReport(
        boundary_score=v,
        skin_tone_score=v,
        motion_score=v,
        identity_score=v,
        passed=passed,
    )


def _decide(features, **kw):
    return decide_lipsync(
        segment_id="s",
        start_ms=0,
        end_ms=features.duration_ms,
        features=features,
        availability=kw.pop("availability", LipSyncAvailability()),
        criteria=_C,
        mode=kw.pop("mode", LipSyncMode.AUTO_ELIGIBLE),
        **kw,
    )


# --- §10.1 资格门 ---------------------------------------------------------


def test_good_segment_is_eligible():
    eligible, reasons = assess_eligibility(_feat(), _C, mode=LipSyncMode.AUTO_ELIGIBLE)
    assert eligible and reasons == []


def test_off_mode_is_ineligible_with_mode_off():
    eligible, reasons = assess_eligibility(_feat(), _C, mode=LipSyncMode.OFF)
    assert not eligible
    assert reasons == [LipSyncIneligibleReason.MODE_OFF]


def test_each_ineligible_reason_fires():
    cases = {
        LipSyncIneligibleReason.NO_PRIMARY_FACE: _feat(face_count=0),
        LipSyncIneligibleReason.MULTIPLE_FACES: _feat(face_count=2),
        LipSyncIneligibleReason.FACE_TOO_SMALL: _feat(face_height_ratio=0.05),
        LipSyncIneligibleReason.OCCLUSION_HIGH: _feat(occlusion_ratio=0.5),
        LipSyncIneligibleReason.LOW_SPEAKER_PROBABILITY: _feat(speaker_probability=0.2),
        LipSyncIneligibleReason.DURATION_OUT_OF_RANGE: _feat(duration_ms=100),
        LipSyncIneligibleReason.HEAD_TURN_TOO_LARGE: _feat(head_turn_deg=80.0),
        LipSyncIneligibleReason.DUB_NOT_ALIGNED: _feat(dub_aligned=False),
    }
    for reason, feat in cases.items():
        eligible, reasons = assess_eligibility(feat, _C, mode=LipSyncMode.AUTO_ELIGIBLE)
        assert not eligible, reason
        assert reason in reasons, reason


def test_geometry_checks_skipped_when_no_single_face():
    # 无脸时不应额外报 FACE_TOO_SMALL/OCCLUSION（脸区几何无意义）
    _, reasons = assess_eligibility(
        _feat(face_count=0, face_height_ratio=0.0, occlusion_ratio=1.0),
        _C,
        mode=LipSyncMode.AUTO_ELIGIBLE,
    )
    assert reasons == [LipSyncIneligibleReason.NO_PRIMARY_FACE]


# --- §10.2 回退阶梯 -------------------------------------------------------


def test_fallback_ladder_order():
    assert (
        resolve_fallback(
            LipSyncAvailability(
                has_similar_original_take=True,
                can_broll_cover=True,
                can_faster_cut=True,
            )
        )
        is LipSyncMethod.ORIGINAL_TAKE
    )
    assert (
        resolve_fallback(
            LipSyncAvailability(
                can_broll_cover=True,
                can_faster_cut=True,
            )
        )
        is LipSyncMethod.BROLL_COVER
    )
    assert (
        resolve_fallback(
            LipSyncAvailability(
                can_faster_cut=True,
            )
        )
        is LipSyncMethod.FASTER_CUT
    )
    # 什么都没有 → 终局保留非口型配音（永远可用）
    assert resolve_fallback(LipSyncAvailability()) is LipSyncMethod.KEEP_UNSYNCED


# --- decide_lipsync ------------------------------------------------------


def test_eligible_intent_plans_gpu_synthesis():
    d = _decide(_feat())
    assert d.eligible and d.method is LipSyncMethod.GPU_SYNTHESIS
    assert not d.needs_review


def test_force_review_flags_eligible_segment():
    d = _decide(_feat(), mode=LipSyncMode.FORCE_REVIEW)
    assert d.method is LipSyncMethod.GPU_SYNTHESIS
    assert d.needs_review
    assert LipSyncReviewReason.FORCE_REVIEW in d.review_reasons


def test_off_mode_keeps_unsynced():
    d = _decide(_feat(), mode=LipSyncMode.OFF)
    assert d.method is LipSyncMethod.KEEP_UNSYNCED
    assert d.eligible is False
    assert LipSyncIneligibleReason.MODE_OFF in d.ineligible_reasons


def test_ineligible_falls_back_with_review():
    d = _decide(_feat(face_count=2), availability=LipSyncAvailability(can_broll_cover=True))
    assert d.method is LipSyncMethod.BROLL_COVER
    assert d.needs_review
    assert LipSyncReviewReason.FALLBACK_USED in d.review_reasons


def test_qa_pass_confirms_gpu_synthesis():
    d = _decide(_feat(), qa=_qa(True), synthesized_artifact_id="art://x")
    assert d.method is LipSyncMethod.GPU_SYNTHESIS
    assert d.synthesized_artifact_id == "art://x"
    assert d.qa is not None and d.qa.passed


def test_qa_fail_auto_degrades_never_blocks():
    # 核心 §13 红线：合格但 QA 未过 → 自动降级 + 警告，绝不停在 GPU_SYNTHESIS
    d = _decide(_feat(), availability=LipSyncAvailability(can_faster_cut=True), qa=_qa(False))
    assert d.method is LipSyncMethod.FASTER_CUT
    assert d.fallback_from is LipSyncMethod.GPU_SYNTHESIS
    assert d.needs_review
    assert LipSyncReviewReason.QA_FAILED in d.review_reasons


def test_qa_fail_with_no_fallback_keeps_unsynced():
    # 无任何回退资源 → 终局 KEEP_UNSYNCED（仍非阻塞）
    d = _decide(_feat(), qa=_qa(False))
    assert d.method is LipSyncMethod.KEEP_UNSYNCED
    assert d.fallback_from is LipSyncMethod.GPU_SYNTHESIS
    assert d.needs_review


def test_regression_qa_pass_without_artifact_auto_degrades():
    # verifier REFUTED：QA 通过但无产物曾产出 GPU_SYNTHESIS 决策被自身护栏判违。
    # 现在应视为合成不完整 → 自动降级，且计划过自身护栏。
    d = _decide(
        _feat(),
        availability=LipSyncAvailability(can_broll_cover=True),
        qa=_qa(True),
        synthesized_artifact_id=None,
    )
    assert d.method is LipSyncMethod.BROLL_COVER
    assert d.fallback_from is LipSyncMethod.GPU_SYNTHESIS
    assert d.needs_review
    assert LipSyncReviewReason.SYNTHESIS_FAILED in d.review_reasons
    plan = plan_lipsync(
        [
            LipSyncSegmentInput(
                "a",
                0,
                3000,
                _feat(),
                LipSyncAvailability(can_broll_cover=True),
                qa=_qa(True),
                synthesized_artifact_id=None,
            )
        ],
        id="p",
        localization_variant_id="v",
        mode=LipSyncMode.AUTO_ELIGIBLE,
        created_at=_T0,
    )
    assert validate_lipsync_plan(plan) == []


# --- 非阻塞不变量 ---------------------------------------------------------


def test_every_decision_has_concrete_nonblocking_method_fuzz():
    modes = [LipSyncMode.OFF, LipSyncMode.AUTO_ELIGIBLE, LipSyncMode.FORCE_REVIEW]
    concrete = set(LipSyncMethod)
    for fc in (0, 1, 2):
        for occ in (0.05, 0.5):
            for spk in (0.2, 0.9):
                for dur in (100, 3000, 60000):
                    for aligned in (True, False):
                        for mode in modes:
                            for qa_passed in (None, True, False):
                                qa = None if qa_passed is None else _qa(qa_passed)
                                for art in (None, "a://x"):  # qa/产物解耦
                                    d = decide_lipsync(
                                        segment_id="s",
                                        start_ms=0,
                                        end_ms=dur,
                                        features=_feat(
                                            face_count=fc,
                                            occlusion_ratio=occ,
                                            speaker_probability=spk,
                                            duration_ms=dur,
                                            dub_aligned=aligned,
                                        ),
                                        availability=LipSyncAvailability(can_broll_cover=True),
                                        criteria=_C,
                                        mode=mode,
                                        qa=qa,
                                        synthesized_artifact_id=art,
                                    )
                                    # 永远有具体方法
                                    assert d.method in concrete
                                    # GPU_SYNTHESIS 只在 QA 过且有产物时出现
                                    if d.method is LipSyncMethod.GPU_SYNTHESIS:
                                        assert d.qa is None or (
                                            d.qa.passed and d.synthesized_artifact_id is not None
                                        )


# --- plan + 护栏 ----------------------------------------------------------


def test_plan_builds_and_validates_clean():
    plan = plan_lipsync(
        [
            LipSyncSegmentInput("a", 0, 3000, _feat()),
            LipSyncSegmentInput(
                "b", 3000, 6000, _feat(face_count=2), LipSyncAvailability(can_broll_cover=True)
            ),
            LipSyncSegmentInput("c", 6000, 9000, _feat(), qa=_qa(False)),  # 降级
        ],
        id="p",
        localization_variant_id="v",
        mode=LipSyncMode.AUTO_ELIGIBLE,
        created_at=_T0,
    )
    assert len(plan.decisions) == 3
    assert is_valid_lipsync_plan(plan)


def test_validate_flags_empty_plan():
    plan = LipSyncPlan(
        id="p",
        localization_variant_id="v",
        mode=LipSyncMode.AUTO_ELIGIBLE,
        decisions=[],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_lipsync_plan(plan)}
    assert LipSyncIssueKind.EMPTY_PLAN in kinds


def test_validate_flags_qa_failed_not_downgraded():
    # 手工构造：GPU_SYNTHESIS 却带 QA 未过（没降级）→ 红线
    plan = LipSyncPlan(
        id="p",
        localization_variant_id="v",
        mode=LipSyncMode.AUTO_ELIGIBLE,
        decisions=[
            LipSyncSegmentDecision(
                segment_id="a",
                start_ms=0,
                end_ms=100,
                eligible=True,
                method=LipSyncMethod.GPU_SYNTHESIS,
                qa=_qa(False),
                rationale="偷偷发出未过 QA 的合成",
            )
        ],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_lipsync_plan(plan)}
    assert LipSyncIssueKind.QA_FAILED_NOT_DOWNGRADED in kinds


def test_validate_flags_qa_pass_without_artifact():
    plan = LipSyncPlan(
        id="p",
        localization_variant_id="v",
        mode=LipSyncMode.AUTO_ELIGIBLE,
        decisions=[
            LipSyncSegmentDecision(
                segment_id="a",
                start_ms=0,
                end_ms=100,
                eligible=True,
                method=LipSyncMethod.GPU_SYNTHESIS,
                qa=_qa(True),
                synthesized_artifact_id=None,
                rationale="QA 过却没产物",
            )
        ],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_lipsync_plan(plan)}
    assert LipSyncIssueKind.QA_PASS_WITHOUT_ARTIFACT in kinds


def test_validate_flags_force_review_not_flagged():
    plan = LipSyncPlan(
        id="p",
        localization_variant_id="v",
        mode=LipSyncMode.FORCE_REVIEW,
        decisions=[
            LipSyncSegmentDecision(
                segment_id="a",
                start_ms=0,
                end_ms=100,
                eligible=True,
                method=LipSyncMethod.GPU_SYNTHESIS,
                needs_review=False,
                rationale="FORCE_REVIEW 下却没标复核",
            )
        ],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_lipsync_plan(plan)}
    assert LipSyncIssueKind.FORCE_REVIEW_NOT_FLAGGED in kinds


def test_validate_flags_downgrade_without_warning():
    plan = LipSyncPlan(
        id="p",
        localization_variant_id="v",
        mode=LipSyncMode.AUTO_ELIGIBLE,
        decisions=[
            LipSyncSegmentDecision(
                segment_id="a",
                start_ms=0,
                end_ms=100,
                eligible=True,
                method=LipSyncMethod.BROLL_COVER,
                fallback_from=LipSyncMethod.GPU_SYNTHESIS,
                needs_review=False,
                rationale="降级却没警告",
            )
        ],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_lipsync_plan(plan)}
    assert LipSyncIssueKind.DOWNGRADE_WITHOUT_WARNING in kinds


def test_validate_flags_off_mode_not_keep_unsynced():
    plan = LipSyncPlan(
        id="p",
        localization_variant_id="v",
        mode=LipSyncMode.OFF,
        decisions=[
            LipSyncSegmentDecision(
                segment_id="a",
                start_ms=0,
                end_ms=100,
                eligible=True,
                method=LipSyncMethod.GPU_SYNTHESIS,
                rationale="OFF 却合成",
            )
        ],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_lipsync_plan(plan)}
    assert LipSyncIssueKind.OFF_MODE_NOT_KEEP_UNSYNCED in kinds


def test_planner_output_always_passes_own_validate_fuzz():
    inputs = []
    for i in range(30):
        inputs.append(
            LipSyncSegmentInput(
                f"s{i}",
                i * 1000,
                i * 1000 + 3000,
                _feat(
                    face_count=i % 3, occlusion_ratio=0.05 + (i % 2) * 0.5, dub_aligned=(i % 2 == 0)
                ),
                LipSyncAvailability(can_broll_cover=(i % 2 == 0)),
                qa=(None if i % 3 == 0 else _qa(i % 2 == 0)),
                # qa/产物解耦：i%4==2 → qa 过但无产物（verifier 反例类），必须降级仍自洽
                synthesized_artifact_id=("a://x" if i % 4 < 2 else None),
            )
        )
    for mode in (LipSyncMode.OFF, LipSyncMode.AUTO_ELIGIBLE, LipSyncMode.FORCE_REVIEW):
        plan = plan_lipsync(
            inputs,
            id="p",
            localization_variant_id="v",
            mode=mode,
            created_at=_T0,
        )
        assert validate_lipsync_plan(plan) == [], f"mode={mode}"
