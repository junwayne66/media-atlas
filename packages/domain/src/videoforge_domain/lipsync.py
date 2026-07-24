"""口型同步资格判断 + 计划 + 回退（docs/modules/43 §10）。纯函数，可复现。

- `assess_eligibility(features, criteria, mode)` → §10.1 资格门（返回全部不符原因）。
- `resolve_fallback(availability)` → §10.2 回退阶梯：原口型相近 Take → 插 B-roll/屏录 →
  加快切镜 → 保留非口型配音（`KEEP_UNSYNCED` 终局永远可用）。
- `decide_lipsync(...)` → 单片段决策；合成失败/QA 不过**自动降级**并置复核警告。
- `plan_lipsync(...)` / `validate_lipsync_plan(...)` → 批量计划 + 护栏。

**红线（§10.2 + §13 验收）**：口型非阻塞。每个片段最终都落到具体、非阻塞的
`LipSyncMethod`；QA 失败必须自动降级并形成警告，绝不让 GPU_SYNTHESIS 带着不过的 QA 蒙混
过关（护栏 `QA_FAILED_NOT_DOWNGRADED`）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

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


@dataclass(frozen=True)
class LipSyncSegmentFeatures:
    """单片段的分析特征（来自人脸检测/说话人/配音对齐；provider/analysis 产出）。"""

    face_count: int
    face_height_ratio: float  # 面部高度 / 画面高度
    occlusion_ratio: float
    speaker_probability: float
    head_turn_deg: float
    duration_ms: int
    dub_aligned: bool


@dataclass(frozen=True)
class LipSyncAvailability:
    """§10.2 回退资源可用性（哪几档回退能用）。"""

    has_similar_original_take: bool = False
    can_broll_cover: bool = False
    can_faster_cut: bool = False


class LipSyncIssueKind(StrEnum):
    EMPTY_PLAN = "EMPTY_PLAN"
    # 红线：QA 未过却仍标 GPU_SYNTHESIS（没有自动降级 → 会把坏口型发出去）
    QA_FAILED_NOT_DOWNGRADED = "QA_FAILED_NOT_DOWNGRADED"
    # GPU 合成 QA 通过却没有产物 artifact（成功声明不完整）
    QA_PASS_WITHOUT_ARTIFACT = "QA_PASS_WITHOUT_ARTIFACT"
    # mode=FORCE_REVIEW 但合格的 GPU 决策没被标复核
    FORCE_REVIEW_NOT_FLAGGED = "FORCE_REVIEW_NOT_FLAGGED"
    # 自动降级（fallback_from 有值）却没形成复核警告（§13：须形成警告）
    DOWNGRADE_WITHOUT_WARNING = "DOWNGRADE_WITHOUT_WARNING"
    # mode=OFF 却有片段不是 KEEP_UNSYNCED
    OFF_MODE_NOT_KEEP_UNSYNCED = "OFF_MODE_NOT_KEEP_UNSYNCED"


@dataclass(frozen=True)
class LipSyncIssue:
    kind: LipSyncIssueKind
    ref: str  # segment_id 或 plan id
    detail: str


def assess_eligibility(
    features: LipSyncSegmentFeatures,
    criteria: LipSyncEligibilityCriteria,
    *,
    mode: LipSyncMode,
) -> tuple[bool, list[LipSyncIneligibleReason]]:
    """§10.1 资格门。返回 (是否合格, 全部不符原因)。mode=OFF 直接不合格。"""
    if mode is LipSyncMode.OFF:
        return False, [LipSyncIneligibleReason.MODE_OFF]

    reasons: list[LipSyncIneligibleReason] = []
    # 单主脸：脸数必须在 [1, max_faces]；否则脸区几何检查无意义，跳过
    if features.face_count < 1:
        reasons.append(LipSyncIneligibleReason.NO_PRIMARY_FACE)
    elif features.face_count > criteria.max_faces:
        reasons.append(LipSyncIneligibleReason.MULTIPLE_FACES)
    else:
        if features.face_height_ratio < criteria.min_face_height_ratio:
            reasons.append(LipSyncIneligibleReason.FACE_TOO_SMALL)
        if features.occlusion_ratio > criteria.max_occlusion_ratio:
            reasons.append(LipSyncIneligibleReason.OCCLUSION_HIGH)
        if features.head_turn_deg > criteria.max_head_turn_deg:
            reasons.append(LipSyncIneligibleReason.HEAD_TURN_TOO_LARGE)
    # 与脸数无关的检查
    if features.speaker_probability < criteria.min_speaker_probability:
        reasons.append(LipSyncIneligibleReason.LOW_SPEAKER_PROBABILITY)
    if not (
        criteria.min_duration_ms <= features.duration_ms <= criteria.max_duration_ms
    ):
        reasons.append(LipSyncIneligibleReason.DURATION_OUT_OF_RANGE)
    if criteria.require_dub_aligned and not features.dub_aligned:
        reasons.append(LipSyncIneligibleReason.DUB_NOT_ALIGNED)

    return (not reasons), reasons


def resolve_fallback(availability: LipSyncAvailability) -> LipSyncMethod:
    """§10.2 回退阶梯：原口型相近 Take → B-roll → 加快切镜 → 保留非口型配音。

    `KEEP_UNSYNCED` 永远可用 → 保证非阻塞。
    """
    if availability.has_similar_original_take:
        return LipSyncMethod.ORIGINAL_TAKE
    if availability.can_broll_cover:
        return LipSyncMethod.BROLL_COVER
    if availability.can_faster_cut:
        return LipSyncMethod.FASTER_CUT
    return LipSyncMethod.KEEP_UNSYNCED


def decide_lipsync(
    *,
    segment_id: str,
    start_ms: int,
    end_ms: int,
    features: LipSyncSegmentFeatures,
    availability: LipSyncAvailability,
    criteria: LipSyncEligibilityCriteria,
    mode: LipSyncMode,
    qa: LipSyncQAReport | None = None,
    synthesized_artifact_id: str | None = None,
) -> LipSyncSegmentDecision:
    """单片段口型决策。

    - `qa=None`：意图计划（尚未合成）——合格片段标 GPU_SYNTHESIS（待执行）。
    - `qa` 给定：合成后结果——`qa.passed` 决定确认 GPU_SYNTHESIS 还是**自动降级**到回退阶梯。
    """
    # mode=OFF：不评估，保留非口型配音
    if mode is LipSyncMode.OFF:
        return LipSyncSegmentDecision(
            segment_id=segment_id, start_ms=start_ms, end_ms=end_ms,
            eligible=False,
            ineligible_reasons=[LipSyncIneligibleReason.MODE_OFF],
            method=LipSyncMethod.KEEP_UNSYNCED,
            rationale="lip_sync_mode=OFF，保留非口型配音",
        )

    eligible, reasons = assess_eligibility(features, criteria, mode=mode)

    if not eligible:
        method = resolve_fallback(availability)
        review = (
            [LipSyncReviewReason.KEPT_UNSYNCED]
            if method is LipSyncMethod.KEEP_UNSYNCED
            else [LipSyncReviewReason.FALLBACK_USED]
        )
        reason_str = "/".join(r.value for r in reasons)
        return LipSyncSegmentDecision(
            segment_id=segment_id, start_ms=start_ms, end_ms=end_ms,
            eligible=False, ineligible_reasons=reasons, method=method,
            needs_review=True, review_reasons=review,
            rationale=f"资格不符（{reason_str}）→ 回退 {method.value}",
        )

    # 合格
    force_review = mode is LipSyncMode.FORCE_REVIEW

    if qa is None:
        # 意图计划：计划 GPU 合成
        return LipSyncSegmentDecision(
            segment_id=segment_id, start_ms=start_ms, end_ms=end_ms,
            eligible=True, method=LipSyncMethod.GPU_SYNTHESIS,
            needs_review=force_review,
            review_reasons=[LipSyncReviewReason.FORCE_REVIEW] if force_review else [],
            rationale=(
                "资格合格 → 计划 GPU 局部脸区合成"
                + ("（FORCE_REVIEW：合成后仍需人工复核）" if force_review else "")
            ),
        )

    # 合成算成功 = QA 通过**且**有产物 artifact。QA 过却无产物同样是"合成不完整"，
    # 必须降级——否则会产出 GPU_SYNTHESIS 却无产物的决策，被自身护栏
    # QA_PASS_WITHOUT_ARTIFACT 判违（build/validate 自洽性，verifier REFUTED 后修）。
    if qa.passed and synthesized_artifact_id is not None:
        return LipSyncSegmentDecision(
            segment_id=segment_id, start_ms=start_ms, end_ms=end_ms,
            eligible=True, method=LipSyncMethod.GPU_SYNTHESIS,
            synthesized_artifact_id=synthesized_artifact_id, qa=qa,
            needs_review=force_review,
            review_reasons=[LipSyncReviewReason.FORCE_REVIEW] if force_review else [],
            rationale="资格合格 + QA 通过 + 有产物 → GPU 合成",
        )

    # 合格但合成不完整（QA 未过，或 QA 过但缺产物）→ 自动降级（§13：不阻塞，形成警告）
    method = resolve_fallback(availability)
    primary = (
        LipSyncReviewReason.QA_FAILED if not qa.passed
        else LipSyncReviewReason.SYNTHESIS_FAILED
    )
    review = [primary]
    review.append(
        LipSyncReviewReason.KEPT_UNSYNCED
        if method is LipSyncMethod.KEEP_UNSYNCED
        else LipSyncReviewReason.FALLBACK_USED
    )
    cause = "QA 未过" if not qa.passed else "QA 通过但缺产物"
    return LipSyncSegmentDecision(
        segment_id=segment_id, start_ms=start_ms, end_ms=end_ms,
        eligible=True, method=method, qa=qa,
        fallback_from=LipSyncMethod.GPU_SYNTHESIS,
        needs_review=True, review_reasons=review,
        rationale=f"资格合格但合成不完整（{cause}）→ 自动降级 {method.value}",
    )


@dataclass(frozen=True)
class LipSyncSegmentInput:
    """plan_lipsync 的单片段输入。"""

    segment_id: str
    start_ms: int
    end_ms: int
    features: LipSyncSegmentFeatures
    availability: LipSyncAvailability = field(default_factory=LipSyncAvailability)
    qa: LipSyncQAReport | None = None
    synthesized_artifact_id: str | None = None


def plan_lipsync(
    inputs: list[LipSyncSegmentInput],
    *,
    id: str,
    localization_variant_id: str,
    mode: LipSyncMode,
    created_at: datetime,
    criteria: LipSyncEligibilityCriteria | None = None,
    provider: str | None = None,
) -> LipSyncPlan:
    """把一批片段输入 → `LipSyncPlan`（每片段一个决策）。"""
    criteria = criteria or LipSyncEligibilityCriteria()
    decisions = [
        decide_lipsync(
            segment_id=inp.segment_id, start_ms=inp.start_ms, end_ms=inp.end_ms,
            features=inp.features, availability=inp.availability,
            criteria=criteria, mode=mode, qa=inp.qa,
            synthesized_artifact_id=inp.synthesized_artifact_id,
        )
        for inp in inputs
    ]
    return LipSyncPlan(
        id=id, localization_variant_id=localization_variant_id, mode=mode,
        criteria=criteria, decisions=decisions, created_at=created_at,
        provider=provider,
    )


def validate_lipsync_plan(plan: LipSyncPlan) -> list[LipSyncIssue]:
    """§10 口型计划护栏；返回全部违规（空 = 通过）。"""
    issues: list[LipSyncIssue] = []

    if not plan.decisions:
        issues.append(LipSyncIssue(
            LipSyncIssueKind.EMPTY_PLAN, plan.id, "计划没有任何决策",
        ))

    for d in plan.decisions:
        # 红线：QA 未过却仍标 GPU_SYNTHESIS（未自动降级）
        if (
            d.method is LipSyncMethod.GPU_SYNTHESIS
            and d.qa is not None
            and not d.qa.passed
        ):
            issues.append(LipSyncIssue(
                LipSyncIssueKind.QA_FAILED_NOT_DOWNGRADED, d.segment_id,
                "QA 未通过却仍标 GPU_SYNTHESIS——必须自动降级到回退阶梯（§10.2/§13）",
            ))
        # GPU QA 通过却无产物
        if (
            d.method is LipSyncMethod.GPU_SYNTHESIS
            and d.qa is not None
            and d.qa.passed
            and d.synthesized_artifact_id is None
        ):
            issues.append(LipSyncIssue(
                LipSyncIssueKind.QA_PASS_WITHOUT_ARTIFACT, d.segment_id,
                "GPU_SYNTHESIS QA 通过却缺 synthesized_artifact_id",
            ))
        # FORCE_REVIEW 模式下合格的 GPU 决策必须被标复核
        if (
            plan.mode is LipSyncMode.FORCE_REVIEW
            and d.method is LipSyncMethod.GPU_SYNTHESIS
            and not (
                d.needs_review
                and LipSyncReviewReason.FORCE_REVIEW in d.review_reasons
            )
        ):
            issues.append(LipSyncIssue(
                LipSyncIssueKind.FORCE_REVIEW_NOT_FLAGGED, d.segment_id,
                "mode=FORCE_REVIEW 但 GPU_SYNTHESIS 决策未标强制复核",
            ))
        # 自动降级必须形成警告
        if d.fallback_from is not None and not d.needs_review:
            issues.append(LipSyncIssue(
                LipSyncIssueKind.DOWNGRADE_WITHOUT_WARNING, d.segment_id,
                f"从 {d.fallback_from.value} 降级却未置 needs_review（§13 须形成警告）",
            ))
        # OFF 模式全部保留非口型配音
        if plan.mode is LipSyncMode.OFF and d.method is not LipSyncMethod.KEEP_UNSYNCED:
            issues.append(LipSyncIssue(
                LipSyncIssueKind.OFF_MODE_NOT_KEEP_UNSYNCED, d.segment_id,
                f"mode=OFF 但片段 method={d.method.value}（应 KEEP_UNSYNCED）",
            ))
    return issues


def is_valid_lipsync_plan(plan: LipSyncPlan) -> bool:
    return not validate_lipsync_plan(plan)
