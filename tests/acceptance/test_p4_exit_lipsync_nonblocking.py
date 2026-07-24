"""P4 Exit 验收 —— 口型失败自动降级、不阻塞 Workflow（docs/modules/43 §13 第 5 条）。

对 40 句构造口型片段（含合成失败/QA 不过/不合格），plan_lipsync 产计划：
- validate_lipsync_plan 恒为空（非阻塞）；
- 任一失败/不合格片段都自动降级到具体回退方法，绝不停在 GPU_SYNTHESIS 且 QA 未过；
- 即使全部合成失败，计划仍成立（KEEP_UNSYNCED 终局永远可用）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from p4_samples import SAMPLES

from videoforge_contracts import LipSyncMethod, LipSyncMode, LipSyncQAReport
from videoforge_domain import (
    LipSyncAvailability,
    LipSyncSegmentFeatures,
    LipSyncSegmentInput,
    plan_lipsync,
    validate_lipsync_plan,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _feat(good: bool) -> LipSyncSegmentFeatures:
    if good:
        return LipSyncSegmentFeatures(1, 0.3, 0.05, 0.9, 10.0, 3000, True)
    return LipSyncSegmentFeatures(2, 0.3, 0.05, 0.9, 10.0, 3000, True)  # 多脸 → 不合格


def _qa(passed: bool) -> LipSyncQAReport:
    v = 0.9 if passed else 0.4
    return LipSyncQAReport(boundary_score=v, skin_tone_score=v, motion_score=v,
                            identity_score=v, passed=passed)


def _inputs():
    """每句一个片段，循环覆盖 4 种情形：合格通过 / 合格QA失败 / 不合格 / 意图。"""
    inputs = []
    i = 0
    for smp in SAMPLES:
        for s in smp.sentences:
            case = i % 4
            avail = LipSyncAvailability(can_broll_cover=True)
            if case == 0:  # 合格 + QA 通过
                inputs.append(LipSyncSegmentInput(
                    s.sentence_id, 0, 3000, _feat(True), avail,
                    qa=_qa(True), synthesized_artifact_id=f"a://{s.sentence_id}"))
            elif case == 1:  # 合格但 QA 未过 → 自动降级
                inputs.append(LipSyncSegmentInput(
                    s.sentence_id, 0, 3000, _feat(True), avail, qa=_qa(False)))
            elif case == 2:  # 不合格 → 回退
                inputs.append(LipSyncSegmentInput(
                    s.sentence_id, 0, 3000, _feat(False), avail))
            else:  # 意图（尚未合成）
                inputs.append(LipSyncSegmentInput(
                    s.sentence_id, 0, 3000, _feat(True), avail))
            i += 1
    return inputs


def test_lipsync_plan_is_never_blocking():
    plan = plan_lipsync(
        _inputs(), id="p4-ls", localization_variant_id="v",
        mode=LipSyncMode.AUTO_ELIGIBLE, created_at=_T0,
    )
    assert validate_lipsync_plan(plan) == []
    # 每片段都有具体方法；QA 未过绝不停在 GPU_SYNTHESIS
    for d in plan.decisions:
        assert d.method in set(LipSyncMethod)
        if d.method is LipSyncMethod.GPU_SYNTHESIS:
            assert d.qa is None or (d.qa.passed and d.synthesized_artifact_id)


def test_all_synthesis_failing_still_resolves():
    # 极端：所有句合成都失败（QA 全不过）+ 无回退资源 → 全部 KEEP_UNSYNCED，计划仍成立
    inputs = [
        LipSyncSegmentInput(
            s.sentence_id, 0, 3000,
            LipSyncSegmentFeatures(1, 0.3, 0.05, 0.9, 10.0, 3000, True),
            LipSyncAvailability(),  # 无回退资源
            qa=_qa(False),
        )
        for smp in SAMPLES for s in smp.sentences
    ]
    plan = plan_lipsync(
        inputs, id="p4-ls2", localization_variant_id="v",
        mode=LipSyncMode.AUTO_ELIGIBLE, created_at=_T0,
    )
    assert validate_lipsync_plan(plan) == []
    assert all(d.method is LipSyncMethod.KEEP_UNSYNCED for d in plan.decisions)
    assert all(d.needs_review for d in plan.decisions)  # 形成警告


def test_off_mode_keeps_all_unsynced():
    plan = plan_lipsync(
        _inputs(), id="p4-ls3", localization_variant_id="v",
        mode=LipSyncMode.OFF, created_at=_T0,
    )
    assert validate_lipsync_plan(plan) == []
    assert all(d.method is LipSyncMethod.KEEP_UNSYNCED for d in plan.decisions)
