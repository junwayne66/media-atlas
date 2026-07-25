"""画面文字本地化决策（docs/modules/43 §6）。纯函数。

- `decide_strategy(track, kind_policy, policy)` → 单条 TextTrack 的策略 + review reasons。
- `plan_text_localization(text_track_set, policy, translations?)` → 完整 `TextLocalizationPlan`。
- `validate_text_localization_plan` → typed `PlanIssue` 列表（BRAND_MARK 授权、UNKNOWN 分类、
  Clean Plate 引用、术语表遵守、layout 溢出）。

**红线**（`43 §6.1`）：BRAND_MARK 决不生成 REDRAW/REPLACE_OVERLAY 决策——只允许 SKIP 或
LOCALIZE_ANNOTATION（旁注不覆盖）；UI 需要授权确认（policy.requires_license_check）。

图像操作（真 inpaint / 排字）不在此层——策略结果为 Provider 领任务（CleanPlateProvider /
TextRedrawProvider）；`plan` 只输出**决策 + 请求**，Provider 未落地属 stop-condition。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    CleanPlateMethod,
    CleanPlateRequest,
    Glossary,
    TextLocalizationKindPolicy,
    TextLocalizationPlan,
    TextLocalizationPolicy,
    TextLocalizationReviewReason,
    TextLocalizationStrategy,
    TextTrack,
    TextTrackKind,
    TextTrackLocalizationDecision,
    TextTrackSet,
)


class TextLocalizationIssueKind(StrEnum):
    EMPTY_PLAN = "EMPTY_PLAN"
    BRAND_MARK_ILLEGAL_STRATEGY = "BRAND_MARK_ILLEGAL_STRATEGY"
    UI_NEEDS_LICENSE_REVIEW = "UI_NEEDS_LICENSE_REVIEW"
    UNKNOWN_KIND_NOT_ROUTED = "UNKNOWN_KIND_NOT_ROUTED"
    KIND_POLICY_MISSING = "KIND_POLICY_MISSING"
    CLEAN_PLATE_MISSING = "CLEAN_PLATE_MISSING"  # REDRAW 无 clean_plate_request_id
    CLEAN_PLATE_UNJUSTIFIED = "CLEAN_PLATE_UNJUSTIFIED"  # 非重绘策略却挂 Clean Plate
    LAYOUT_OVERFLOW = "LAYOUT_OVERFLOW"  # expansion > policy.max
    GLOSSARY_MUST_KEEP_TERM_LOST = "GLOSSARY_MUST_KEEP_TERM_LOST"
    TRANSLATED_TEXT_MISSING = "TRANSLATED_TEXT_MISSING"  # 策略需译文但未提供
    TRANSLATED_TEXT_ILLEGAL = "TRANSLATED_TEXT_ILLEGAL"  # SKIP/KEEP_AS_IS 却提供了译文


@dataclass(frozen=True)
class TextLocalizationIssue:
    kind: TextLocalizationIssueKind
    ref: str
    detail: str


_TRANSLATION_REQUIRED = {
    TextLocalizationStrategy.REDRAW,
    TextLocalizationStrategy.REPLACE_OVERLAY,
    TextLocalizationStrategy.LOCALIZE_ANNOTATION,
}
_TRANSLATION_FORBIDDEN = {
    TextLocalizationStrategy.KEEP_AS_IS,
    TextLocalizationStrategy.SKIP,
}


def _find_kind_policy(
    policy: TextLocalizationPolicy,
    kind: TextTrackKind,
) -> TextLocalizationKindPolicy | None:
    for p in policy.per_kind:
        if p.kind is kind:
            return p
    return None


def _occlusion_of(track: TextTrack) -> float:
    """从 observations 里估算遮挡比：任一 obs.occluded=True 则 1/N。无 obs → 0。"""
    if not track.observations:
        return 0.0
    occ = sum(1 for o in track.observations if o.occluded)
    return occ / len(track.observations)


def decide_strategy(
    track: TextTrack,
    *,
    policy: TextLocalizationPolicy,
    translated_text: str | None = None,
    layout_expansion_ratio: float | None = None,
) -> TextTrackLocalizationDecision:
    """按 kind + confidence + occlusion + layout 决策单条 track 的策略。

    - BRAND_MARK 永远走 SKIP（人工确认授权）；kind_policy 里的 default_strategy 会被强制覆盖。
    - UI 若 policy.requires_license_check=True → LOCALIZE_ANNOTATION + review。
    - UNKNOWN → SKIP + UNKNOWN_KIND review。
    - 低 OCR 置信度 / 遮挡过高 / layout 溢出 → 退到 kind_policy.fallback_strategy + review。
    """
    reasons: list[TextLocalizationReviewReason] = []

    # 硬红线：BRAND_MARK 无论 policy 怎么配置都不作为普通翻译文字
    if track.kind is TextTrackKind.BRAND_MARK:
        return TextTrackLocalizationDecision(
            source_track_id=track.id,
            source_text=track.text,
            source_kind=track.kind,
            target_language=policy.target_language,
            strategy=TextLocalizationStrategy.SKIP,
            translated_text=None,
            needs_review=True,
            review_reasons=[TextLocalizationReviewReason.LICENSE_UNCONFIRMED],
            rationale="BRAND_MARK 涉品牌授权，默认 SKIP + 交人工确认（§6.1 硬红线）",
        )

    # UNKNOWN → SKIP + 人工分类
    if track.kind is TextTrackKind.UNKNOWN:
        return TextTrackLocalizationDecision(
            source_track_id=track.id,
            source_text=track.text,
            source_kind=track.kind,
            target_language=policy.target_language,
            strategy=TextLocalizationStrategy.SKIP,
            translated_text=None,
            needs_review=True,
            review_reasons=[TextLocalizationReviewReason.UNKNOWN_KIND],
            rationale="TextTrackKind.UNKNOWN 无法自动路由，交人工分类",
        )

    kind_policy = _find_kind_policy(policy, track.kind)
    if kind_policy is None:
        # 无 kind 配置：安全默认——SKIP + review
        return TextTrackLocalizationDecision(
            source_track_id=track.id,
            source_text=track.text,
            source_kind=track.kind,
            target_language=policy.target_language,
            strategy=TextLocalizationStrategy.SKIP,
            translated_text=None,
            needs_review=True,
            review_reasons=[TextLocalizationReviewReason.UNKNOWN_KIND],
            rationale=(f"policy 未为 kind={track.kind.value} 配置策略，默认 SKIP + 交人工"),
        )

    # UI 授权确认
    if kind_policy.requires_license_check:
        return TextTrackLocalizationDecision(
            source_track_id=track.id,
            source_text=track.text,
            source_kind=track.kind,
            target_language=policy.target_language,
            strategy=TextLocalizationStrategy.LOCALIZE_ANNOTATION,
            translated_text=translated_text,
            needs_review=True,
            review_reasons=[TextLocalizationReviewReason.LICENSE_UNCONFIRMED],
            rationale=(f"{track.kind.value} 需授权确认，默认旁注（LOCALIZE_ANNOTATION）而非覆盖"),
        )

    strategy = kind_policy.default_strategy
    if track.low_confidence or track.confidence < kind_policy.min_confidence_for_auto:
        reasons.append(TextLocalizationReviewReason.LOW_OCR_CONFIDENCE)
        strategy = kind_policy.fallback_strategy

    occlusion = _occlusion_of(track)
    if strategy is TextLocalizationStrategy.REDRAW and (
        not kind_policy.allow_redraw or occlusion > policy.max_occlusion_for_redraw
    ):
        if occlusion > policy.max_occlusion_for_redraw:
            reasons.append(TextLocalizationReviewReason.OCCLUSION_HIGH)
        strategy = kind_policy.fallback_strategy

    if (
        layout_expansion_ratio is not None
        and layout_expansion_ratio > policy.max_layout_expansion_ratio
        and strategy in _TRANSLATION_REQUIRED
    ):
        reasons.append(TextLocalizationReviewReason.LAYOUT_OVERFLOW)
        strategy = kind_policy.fallback_strategy

    return TextTrackLocalizationDecision(
        source_track_id=track.id,
        source_text=track.text,
        source_kind=track.kind,
        target_language=policy.target_language,
        strategy=strategy,
        translated_text=translated_text if strategy in _TRANSLATION_REQUIRED else None,
        layout_expansion_ratio=layout_expansion_ratio,
        needs_review=bool(reasons),
        review_reasons=reasons,
        rationale=(
            f"{track.kind.value} 按 policy 默认 {kind_policy.default_strategy.value}"
            + (
                f"，回退至 {strategy.value}（{','.join(r.value for r in reasons)}）"
                if reasons
                else ""
            )
        ),
    )


def _clean_plate_request_for(
    track: TextTrack,
    decision: TextTrackLocalizationDecision,
    *,
    request_id: str,
) -> CleanPlateRequest | None:
    """REDRAW 策略生成 BACKGROUND_ESTIMATE 请求；其它策略无需 Clean Plate。"""
    if decision.strategy is not TextLocalizationStrategy.REDRAW:
        return None
    return CleanPlateRequest(
        id=request_id,
        source_track_id=track.id,
        source_artifact_id=track.source_artifact_id or "unknown",
        frame_start_ms=track.start_ms,
        frame_end_ms=track.end_ms,
        method=CleanPlateMethod.BACKGROUND_ESTIMATE,
    )


def plan_text_localization(
    text_track_set: TextTrackSet,
    *,
    policy: TextLocalizationPolicy,
    plan_id: str,
    created_at: datetime,
    translations: Mapping[str, str] | None = None,
    layout_ratios: Mapping[str, float] | None = None,
    provider: str | None = None,
) -> TextLocalizationPlan:
    """把 TextTrackSet 转为 TextLocalizationPlan：每 track 一 decision，REDRAW 生成 Clean Plate。

    - `translations`: 可选 dict[source_track_id, translated_text]
      （由 TRA/翻译服务预先产出）。
    - `layout_ratios`: 可选 dict[source_track_id, ratio]（`|target|/|source|`；
      由布局测量服务产出）。
    """
    tr = translations or {}
    lr = layout_ratios or {}
    decisions: list[TextTrackLocalizationDecision] = []
    requests: list[CleanPlateRequest] = []
    for i, track in enumerate(text_track_set.tracks):
        decision = decide_strategy(
            track,
            policy=policy,
            translated_text=tr.get(track.id),
            layout_expansion_ratio=lr.get(track.id),
        )
        req = _clean_plate_request_for(track, decision, request_id=f"cp-{i}")
        if req is not None:
            requests.append(req)
            # 绑定 request id 到 decision
            decision = decision.model_copy(update={"clean_plate_request_id": req.id})
        decisions.append(decision)
    return TextLocalizationPlan(
        id=plan_id,
        source_text_track_set_id=text_track_set.id,
        policy_id=policy.id,
        target_language=policy.target_language,
        decisions=decisions,
        clean_plate_requests=requests,
        created_at=created_at,
        provider=provider,
    )


def _term_present_ci(text: str, term: str) -> bool:
    """简易大小写不敏感包含检测——与 domain.localization._text_contains_term 语义弱化版
    （不做 word-boundary）；因为屏幕文字通常是短语，子串命中足够。"""
    if not term:
        return True
    return term.lower() in text.lower()


def validate_text_localization_plan(
    plan: TextLocalizationPlan,
    *,
    policy: TextLocalizationPolicy,
    glossary: Glossary | None = None,
) -> list[TextLocalizationIssue]:
    """本地化计划护栏——返回全部违规（空 = 通过）。"""
    issues: list[TextLocalizationIssue] = []
    if not plan.decisions:
        issues.append(
            TextLocalizationIssue(TextLocalizationIssueKind.EMPTY_PLAN, plan.id, "计划无决策")
        )
        return issues
    req_ids = {r.id for r in plan.clean_plate_requests}
    for d in plan.decisions:
        ref = d.source_track_id
        # 硬红线：BRAND_MARK 不允许 REDRAW / REPLACE_OVERLAY
        if d.source_kind is TextTrackKind.BRAND_MARK and d.strategy in {
            TextLocalizationStrategy.REDRAW,
            TextLocalizationStrategy.REPLACE_OVERLAY,
        }:
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.BRAND_MARK_ILLEGAL_STRATEGY,
                    ref,
                    f"BRAND_MARK 不得走 {d.strategy.value}（§6.1 授权红线）",
                )
            )
        # UNKNOWN 不路由
        if d.source_kind is TextTrackKind.UNKNOWN and d.strategy not in {
            TextLocalizationStrategy.SKIP,
        }:
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.UNKNOWN_KIND_NOT_ROUTED,
                    ref,
                    f"UNKNOWN kind 应 SKIP，实际 {d.strategy.value}",
                )
            )
        # UI 未走 review 的红线
        kp = _find_kind_policy(policy, d.source_kind)
        if kp is None:
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.KIND_POLICY_MISSING,
                    ref,
                    f"policy 未为 kind={d.source_kind.value} 配置",
                )
            )
        elif kp.requires_license_check and not d.needs_review:
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.UI_NEEDS_LICENSE_REVIEW,
                    ref,
                    f"kind {d.source_kind.value} 需授权确认但 decision 未标 needs_review",
                )
            )
        # Clean Plate 引用一致
        if d.strategy is TextLocalizationStrategy.REDRAW and not d.clean_plate_request_id:
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.CLEAN_PLATE_MISSING,
                    ref,
                    "REDRAW 必须挂 clean_plate_request_id",
                )
            )
        if d.clean_plate_request_id and d.strategy is not TextLocalizationStrategy.REDRAW:
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.CLEAN_PLATE_UNJUSTIFIED,
                    ref,
                    f"策略 {d.strategy.value} 不需要 Clean Plate 却挂了引用",
                )
            )
        if d.clean_plate_request_id and d.clean_plate_request_id not in req_ids:
            # pydantic model_validator 已拦，此处双保险
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.CLEAN_PLATE_MISSING,
                    ref,
                    f"clean_plate_request_id {d.clean_plate_request_id!r} 不在 plan 中",
                )
            )
        # 译文与策略一致
        if d.strategy in _TRANSLATION_REQUIRED and not d.translated_text:
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.TRANSLATED_TEXT_MISSING,
                    ref,
                    f"策略 {d.strategy.value} 需要 translated_text",
                )
            )
        if d.strategy in _TRANSLATION_FORBIDDEN and d.translated_text:
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.TRANSLATED_TEXT_ILLEGAL,
                    ref,
                    f"策略 {d.strategy.value} 不应带 translated_text",
                )
            )
        # layout 溢出
        if (
            d.layout_expansion_ratio is not None
            and d.layout_expansion_ratio > policy.max_layout_expansion_ratio
            and d.strategy in _TRANSLATION_REQUIRED
        ):
            issues.append(
                TextLocalizationIssue(
                    TextLocalizationIssueKind.LAYOUT_OVERFLOW,
                    ref,
                    f"layout 扩张 {d.layout_expansion_ratio:.2f} > "
                    f"policy.max {policy.max_layout_expansion_ratio:.2f}",
                )
            )
        # 术语表：preserve_source 术语在源里出现即必须在译文保留
        if glossary is not None and d.translated_text:
            for e in glossary.entries:
                if not e.preserve_source:
                    continue
                if _term_present_ci(d.source_text, e.source_term) and not _term_present_ci(
                    d.translated_text, e.source_term
                ):
                    issues.append(
                        TextLocalizationIssue(
                            TextLocalizationIssueKind.GLOSSARY_MUST_KEEP_TERM_LOST,
                            ref,
                            f"术语表要求原样保留 {e.source_term!r}，译文未含",
                        )
                    )
    return issues


def is_valid_text_localization_plan(
    plan: TextLocalizationPlan,
    *,
    policy: TextLocalizationPolicy,
    glossary: Glossary | None = None,
) -> bool:
    return not validate_text_localization_plan(plan, policy=policy, glossary=glossary)
