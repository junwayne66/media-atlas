"""时长拟合决策 + 护栏（docs/modules/43 §8）。纯函数，可复现。

§8 五步**顺序**回退（目标语言比原句长/短时按序尝试，命中即止）：

1. `LLM_REWRITE` —— LLM 改写更短/更长，但 **Claim 不变**（provider 产出，domain 只判定
   其估算是否落入自然区间）。
2. `TTS_SPEED` —— TTS 语速在自然区间 [0.92, 1.08]（模板可配）微调。
3. `BROLL_ADJUST` —— 相邻 B-roll/停顿/镜头 Hold 借/填时间。
4. `TIME_STRETCH` —— 对**非人脸**镜头做小幅（默认 ±5%）时间伸缩。
5. `BEAT_REPLAN` —— 仍超限则重排 Beat/加切镜 → 人工（NEEDS_REVIEW）。

**红线（禁止极端压速）**：任何 `OK_*` 决策的最终语速 `final_ratio` 必须落在自然区间内。
speed 单独不够时，只允许"借时间/伸缩画面"把语速钳到自然边界；绝不返回 OK 却用 0.7x 这类
极端压速——这类一律路由到 NEEDS_REVIEW（重排/人工）。护栏 `validate_duration_fit_plan`
把这条不变量变成可检测的 `EXTREME_SPEED`。

每句忠实记录 `fit_method` 与 `final_ratio`（§8 每句必录）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    DurationFitDecision,
    DurationFitPlan,
    DurationFitStatus,
    DurationFitStrategy,
)

# §8 TTS 语速自然区间（模板可覆盖，此为默认；与 VF-404 domain.tts 一致）
NATURAL_SPEED_MIN = 0.92
NATURAL_SPEED_MAX = 1.08
# 非人脸镜头时间伸缩默认绝对幅度（±5%）
DEFAULT_STRETCH_MAX_ABS_RATIO = 0.05
# "无需拟合"容差：|est/target - 1| ≤ 该值即视为已在预算（默认 ±2%）
DEFAULT_UNCHANGED_TOLERANCE = 0.02


@dataclass(frozen=True)
class DurationFitInput:
    """单句拟合输入。

    - `estimated_ms`：适配稿的 TTS 估算时长（VF-404 estimate）。
    - `target_ms`：目标镜头/预算时长（> 0）。
    - `rewritten_estimate_ms`：§8 步 1 —— LLM 改写候选的新估算（provider 产出）；
      `None` = 没有可用改写。
    - `broll_slack_ms`：§8 步 3 —— 相邻 B-roll/停顿/Hold 可吸收/填充的时间（≥ 0）。
    - `face_locked`：True 时该句锁口型/人脸，**禁止** §8 步 4 时间伸缩。
    """

    sentence_id: str
    estimated_ms: int
    target_ms: int
    rewritten_estimate_ms: int | None = None
    broll_slack_ms: int = 0
    face_locked: bool = False


class DurationFitIssueKind(StrEnum):
    EMPTY_PLAN = "EMPTY_PLAN"
    # 红线：OK_* 决策的 final_ratio 落在自然区间外（极端压速被伪装成"成功"）
    EXTREME_SPEED = "EXTREME_SPEED"
    # 状态与 fit_method 不自洽（UNCHANGED↔None / FITTED↔method）
    STATUS_METHOD_INCONSISTENT = "STATUS_METHOD_INCONSISTENT"
    # NEEDS_REVIEW 却没有任何 review_reasons（人工必须知道为什么）
    REVIEW_WITHOUT_REASON = "REVIEW_WITHOUT_REASON"


@dataclass(frozen=True)
class DurationFitIssue:
    kind: DurationFitIssueKind
    ref: str  # sentence_id 或 plan id
    detail: str


# 合同要求 final_ratio > 0；极端过短句（est≪target）raw 可能舍入到 0，用极小正下限兜底
# （这类句必是 NEEDS_REVIEW，下限只为满足合同 > 0，不改变护栏对 OK_* 的判定）。
_MIN_FINAL_RATIO = 0.0001


def _final_ratio(x: float) -> float:
    return max(round(x, 4), _MIN_FINAL_RATIO)


def decide_duration_fit(
    inp: DurationFitInput,
    *,
    natural_min: float = NATURAL_SPEED_MIN,
    natural_max: float = NATURAL_SPEED_MAX,
    stretch_max_abs_ratio: float = DEFAULT_STRETCH_MAX_ABS_RATIO,
    unchanged_tolerance: float = DEFAULT_UNCHANGED_TOLERANCE,
) -> DurationFitDecision:
    """按 §8 五步顺序对单句做拟合决策。

    不变量：返回 `OK_UNCHANGED` / `OK_FITTED` 时，`final_ratio`（最终语速倍数）恒落在
    `[natural_min, natural_max]` 内——超区间只会得到 `NEEDS_REVIEW`（禁止极端压速）。
    """
    sid = inp.sentence_id
    est = inp.estimated_ms
    target = inp.target_ms

    # 退化：无语音（空句）——无可合成，不需拟合
    if est <= 0:
        return DurationFitDecision(
            sentence_id=sid, estimated_ms=max(est, 0), target_ms=target,
            fit_method=None, final_ratio=1.0,
            status=DurationFitStatus.OK_UNCHANGED,
            rationale="无语音（estimated_ms=0），无需拟合",
        )

    raw = est / target  # 需要的语速倍数（>1 太长要提速；<1 太短要放慢/填充）
    # 无需拟合的容差带必须夹在自然区间内——否则调用方传入比容差还窄的 natural_min 时，
    # 会产出超区间的 OK_UNCHANGED 而被自身护栏判 EXTREME_SPEED（build/validate 自洽性）。
    unchanged_lo = max(1.0 - unchanged_tolerance, natural_min)
    unchanged_hi = min(1.0 + unchanged_tolerance, natural_max)

    # 0. 已在预算容差内
    if unchanged_lo <= raw <= unchanged_hi:
        return DurationFitDecision(
            sentence_id=sid, estimated_ms=est, target_ms=target,
            fit_method=None, final_ratio=_final_ratio(raw),
            status=DurationFitStatus.OK_UNCHANGED,
            rationale=(
                f"估算 {est}ms 相对目标 {target}ms 偏差 {(raw - 1):+.1%} "
                f"在容差 ±{unchanged_tolerance:.0%} 内，无需拟合"
            ),
        )

    # 1. LLM_REWRITE：改写候选估算落入自然区间即采纳（Claim 由 provider 保证不变）
    if inp.rewritten_estimate_ms is not None and inp.rewritten_estimate_ms > 0:
        rr = inp.rewritten_estimate_ms / target
        if natural_min <= rr <= natural_max:
            return DurationFitDecision(
                sentence_id=sid, estimated_ms=est, target_ms=target,
                fit_method=DurationFitStrategy.LLM_REWRITE, final_ratio=_final_ratio(rr),
                status=DurationFitStatus.OK_FITTED,
                rationale=(
                    f"LLM 改写后估算 {inp.rewritten_estimate_ms}ms，"
                    f"语速 {rr:.3f}x 落入自然区间 [{natural_min}, {natural_max}]"
                ),
            )

    # 2. TTS_SPEED：原估算语速已在自然区间
    if natural_min <= raw <= natural_max:
        return DurationFitDecision(
            sentence_id=sid, estimated_ms=est, target_ms=target,
            fit_method=DurationFitStrategy.TTS_SPEED, final_ratio=_final_ratio(raw),
            status=DurationFitStatus.OK_FITTED,
            rationale=(
                f"TTS 语速 {raw:.3f}x 在自然区间 [{natural_min}, {natural_max}]"
            ),
        )

    # 语速单独不够。把语速钳到最近的自然边界，剩余时间差交给借时间/伸缩。
    too_long = raw > natural_max
    bound = natural_max if too_long else natural_min
    speech_at_bound = est / bound  # 钳到自然边界后的语音时长
    gap = abs(speech_at_bound - target)  # 与目标仍差的毫秒（借/填的量）

    # 3. BROLL_ADJUST：相邻 B-roll/停顿/Hold 吸收 gap，语速停在自然边界
    if gap <= inp.broll_slack_ms:
        verb = "借" if too_long else "填"
        return DurationFitDecision(
            sentence_id=sid, estimated_ms=est, target_ms=target,
            fit_method=DurationFitStrategy.BROLL_ADJUST, final_ratio=_final_ratio(bound),
            status=DurationFitStatus.OK_FITTED,
            rationale=(
                f"语速钳到自然边界 {bound:.2f}x，相邻 B-roll/停顿{verb} {gap:.0f}ms"
                f"（slack {inp.broll_slack_ms}ms）"
            ),
        )

    # 4. TIME_STRETCH：非人脸镜头小幅时间伸缩吸收剩余（人脸锁定禁止）
    if not inp.face_locked:
        stretch_ratio = gap / target
        if stretch_ratio <= stretch_max_abs_ratio:
            sign = "拉长" if too_long else "缩短"
            return DurationFitDecision(
                sentence_id=sid, estimated_ms=est, target_ms=target,
                fit_method=DurationFitStrategy.TIME_STRETCH, final_ratio=_final_ratio(bound),
                status=DurationFitStatus.OK_FITTED,
                rationale=(
                    f"语速钳到自然边界 {bound:.2f}x，非人脸镜头{sign}时间伸缩 "
                    f"{stretch_ratio:.1%}（≤ ±{stretch_max_abs_ratio:.0%}）"
                ),
            )

    # 5. BEAT_REPLAN：借时间/伸缩都不够 → 重排 Beat/加切镜 → 人工。禁止极端压速。
    reasons = ["NEEDS_BEAT_REPLAN", "EXTREME_SPEED_REFUSED"]
    if inp.face_locked and too_long:
        reasons.append("FACE_LOCKED_NO_STRETCH")
    return DurationFitDecision(
        sentence_id=sid, estimated_ms=est, target_ms=target,
        fit_method=DurationFitStrategy.BEAT_REPLAN, final_ratio=_final_ratio(raw),
        status=DurationFitStatus.NEEDS_REVIEW,
        rationale=(
            f"要命中目标需语速 {raw:g}x 超自然区间 [{natural_min}, {natural_max}]，"
            f"B-roll slack/时间伸缩不足；须重排 Beat 或人工（禁止极端压速）"
        ),
        review_reasons=reasons,
    )


def plan_duration_fit(
    inputs: list[DurationFitInput],
    *,
    id: str,
    localization_variant_id: str,
    created_at: datetime,
    natural_min: float = NATURAL_SPEED_MIN,
    natural_max: float = NATURAL_SPEED_MAX,
    stretch_max_abs_ratio: float = DEFAULT_STRETCH_MAX_ABS_RATIO,
    unchanged_tolerance: float = DEFAULT_UNCHANGED_TOLERANCE,
) -> DurationFitPlan:
    """把一批句子输入 → `DurationFitPlan`（每句一个 `DurationFitDecision`）。

    自然区间与伸缩幅度写入 plan，供 `validate_duration_fit_plan` 复用同一套阈值。
    """
    decisions = [
        decide_duration_fit(
            inp, natural_min=natural_min, natural_max=natural_max,
            stretch_max_abs_ratio=stretch_max_abs_ratio,
            unchanged_tolerance=unchanged_tolerance,
        )
        for inp in inputs
    ]
    return DurationFitPlan(
        id=id,
        localization_variant_id=localization_variant_id,
        decisions=decisions,
        natural_speed_min=natural_min,
        natural_speed_max=natural_max,
        stretch_max_abs_ratio=stretch_max_abs_ratio,
        created_at=created_at,
    )


def validate_duration_fit_plan(plan: DurationFitPlan) -> list[DurationFitIssue]:
    """§8 时长拟合护栏；返回全部违规（空 = 通过）。

    自然区间取自 plan 自身（`natural_speed_min/max`），所以手工构造的计划也用它声明的
    区间来判定"极端压速"。
    """
    issues: list[DurationFitIssue] = []
    lo = plan.natural_speed_min
    hi = plan.natural_speed_max

    if not plan.decisions:
        issues.append(DurationFitIssue(
            DurationFitIssueKind.EMPTY_PLAN, plan.id,
            "计划没有任何 decision",
        ))

    for d in plan.decisions:
        ok_status = d.status in (
            DurationFitStatus.OK_UNCHANGED, DurationFitStatus.OK_FITTED,
        )
        # 红线：OK_* 的最终语速必须在自然区间内
        if ok_status and not (lo <= d.final_ratio <= hi):
            issues.append(DurationFitIssue(
                DurationFitIssueKind.EXTREME_SPEED, d.sentence_id,
                f"status={d.status.value} 但 final_ratio={d.final_ratio} "
                f"超自然区间 [{lo}, {hi}]（禁止极端压速）",
            ))
        # 状态 ↔ fit_method 自洽
        if d.status is DurationFitStatus.OK_UNCHANGED and d.fit_method is not None:
            issues.append(DurationFitIssue(
                DurationFitIssueKind.STATUS_METHOD_INCONSISTENT, d.sentence_id,
                f"OK_UNCHANGED 不应带 fit_method={d.fit_method.value}",
            ))
        if d.status is DurationFitStatus.OK_FITTED and d.fit_method is None:
            issues.append(DurationFitIssue(
                DurationFitIssueKind.STATUS_METHOD_INCONSISTENT, d.sentence_id,
                "OK_FITTED 必须记录 fit_method",
            ))
        # NEEDS_REVIEW 必须给出原因
        if d.status is DurationFitStatus.NEEDS_REVIEW and not d.review_reasons:
            issues.append(DurationFitIssue(
                DurationFitIssueKind.REVIEW_WITHOUT_REASON, d.sentence_id,
                "NEEDS_REVIEW 必须带 review_reasons",
            ))
    return issues


def is_valid_duration_fit_plan(plan: DurationFitPlan) -> bool:
    return not validate_duration_fit_plan(plan)
