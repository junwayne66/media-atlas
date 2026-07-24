"""VF-405 时长拟合 domain 测试：§8 五步顺序 + 禁止极端压速红线 + 护栏。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    DurationFitDecision,
    DurationFitPlan,
    DurationFitStatus,
    DurationFitStrategy,
)
from videoforge_domain import (
    DurationFitInput,
    DurationFitIssueKind,
    decide_duration_fit,
    is_valid_duration_fit_plan,
    plan_duration_fit,
    validate_duration_fit_plan,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)
_MIN = 0.92
_MAX = 1.08


def _d(sid: str, **kw) -> DurationFitInput:
    return DurationFitInput(sentence_id=sid, **kw)


# --- 逐步选择 ---------------------------------------------------------------

def test_within_tolerance_is_unchanged():
    d = decide_duration_fit(_d("s", estimated_ms=3000, target_ms=3000))
    assert d.status is DurationFitStatus.OK_UNCHANGED
    assert d.fit_method is None
    assert d.final_ratio == 1.0


def test_empty_speech_is_unchanged():
    d = decide_duration_fit(_d("s", estimated_ms=0, target_ms=3000))
    assert d.status is DurationFitStatus.OK_UNCHANGED
    assert d.final_ratio == 1.0  # 合同要求 final_ratio > 0


def test_natural_speed_uses_tts_speed():
    d = decide_duration_fit(_d("s", estimated_ms=3200, target_ms=3000))
    assert d.status is DurationFitStatus.OK_FITTED
    assert d.fit_method is DurationFitStrategy.TTS_SPEED
    assert _MIN <= d.final_ratio <= _MAX


def test_rewrite_preferred_when_it_lands_in_band():
    # 原始 1.2x 超区间；改写候选 3100/3000=1.033x 落入区间 → LLM_REWRITE 先命中
    d = decide_duration_fit(
        _d("s", estimated_ms=3600, target_ms=3000, rewritten_estimate_ms=3100)
    )
    assert d.status is DurationFitStatus.OK_FITTED
    assert d.fit_method is DurationFitStrategy.LLM_REWRITE
    assert _MIN <= d.final_ratio <= _MAX


def test_rewrite_still_out_of_band_falls_through():
    # 改写候选仍 3500/3000=1.167x 超区间 → 不采纳 rewrite，继续后续步骤
    d = decide_duration_fit(
        _d("s", estimated_ms=3600, target_ms=3000, rewritten_estimate_ms=3500,
           broll_slack_ms=0)
    )
    assert d.fit_method is not DurationFitStrategy.LLM_REWRITE


def test_broll_absorbs_overflow():
    # 1.2x 太长；语速钳到 1.08 后 gap≈333ms，slack 500 → BROLL_ADJUST
    d = decide_duration_fit(
        _d("s", estimated_ms=3600, target_ms=3000, broll_slack_ms=500)
    )
    assert d.status is DurationFitStatus.OK_FITTED
    assert d.fit_method is DurationFitStrategy.BROLL_ADJUST
    assert d.final_ratio == _MAX  # 语速停在自然边界


def test_broll_fills_deficit_when_too_short():
    # 太短：2000/3000=0.667x；钳到 0.92 后 gap≈826ms，slack 1000 → BROLL 填充
    d = decide_duration_fit(
        _d("s", estimated_ms=2000, target_ms=3000, broll_slack_ms=1000)
    )
    assert d.status is DurationFitStatus.OK_FITTED
    assert d.fit_method is DurationFitStrategy.BROLL_ADJUST
    assert d.final_ratio == _MIN


def test_small_overrun_uses_time_stretch():
    # 1.1x：钳到 1.08 后 gap≈56ms，stretch_ratio≈1.85% ≤5% → TIME_STRETCH
    d = decide_duration_fit(_d("s", estimated_ms=3300, target_ms=3000))
    assert d.status is DurationFitStatus.OK_FITTED
    assert d.fit_method is DurationFitStrategy.TIME_STRETCH
    assert d.final_ratio == _MAX


def test_face_locked_forbids_time_stretch():
    # 同上但人脸锁定 → 不能伸缩 → 落到 BEAT_REPLAN / NEEDS_REVIEW
    d = decide_duration_fit(
        _d("s", estimated_ms=3300, target_ms=3000, face_locked=True)
    )
    assert d.status is DurationFitStatus.NEEDS_REVIEW
    assert d.fit_method is DurationFitStrategy.BEAT_REPLAN
    assert "FACE_LOCKED_NO_STRETCH" in d.review_reasons


def test_extreme_ratio_routes_to_review_never_ok():
    # 2.0x 极端 → 绝不 OK；路由到 NEEDS_REVIEW（禁止极端压速）
    d = decide_duration_fit(_d("s", estimated_ms=6000, target_ms=3000))
    assert d.status is DurationFitStatus.NEEDS_REVIEW
    assert d.fit_method is DurationFitStrategy.BEAT_REPLAN
    assert "EXTREME_SPEED_REFUSED" in d.review_reasons
    # final_ratio 记录真实需要的极端值以示严重程度
    assert d.final_ratio == 2.0


# --- 红线不变量：OK_* 的 final_ratio 恒在自然区间 -------------------------

def test_ok_decisions_never_exceed_natural_band_fuzz():
    for est in range(500, 8001, 137):
        for target in (2000, 3000, 5000):
            for slack in (0, 300, 2000):
                for face in (False, True):
                    for rw in (None, target):  # rw==target → 1.0x 完美改写
                        d = decide_duration_fit(_d(
                            "s", estimated_ms=est, target_ms=target,
                            broll_slack_ms=slack, face_locked=face,
                            rewritten_estimate_ms=rw,
                        ))
                        if d.status in (
                            DurationFitStatus.OK_UNCHANGED,
                            DurationFitStatus.OK_FITTED,
                        ):
                            assert _MIN <= d.final_ratio <= _MAX, (
                                f"OK 决策语速越界: est={est} target={target} "
                                f"slack={slack} face={face} rw={rw} "
                                f"ratio={d.final_ratio} method={d.fit_method}"
                            )


def test_custom_natural_bounds_thread_through():
    # 收窄自然区间到 [0.98, 1.02] 后，1.05x 不再算自然速度
    d = decide_duration_fit(
        _d("s", estimated_ms=3150, target_ms=3000),
        natural_min=0.98, natural_max=1.02,
    )
    # 1.05x 超收窄区间，slack/stretch 不足 → 不是 TTS_SPEED
    assert d.fit_method is not DurationFitStrategy.TTS_SPEED


# --- plan_duration_fit + 护栏 ----------------------------------------------

def test_plan_builds_and_validates_clean():
    plan = plan_duration_fit(
        [
            _d("a", estimated_ms=3200, target_ms=3000),
            _d("b", estimated_ms=3000, target_ms=3000),
            _d("c", estimated_ms=6000, target_ms=3000),  # NEEDS_REVIEW，仍合规
        ],
        id="p", localization_variant_id="v", created_at=_T0,
    )
    assert len(plan.decisions) == 3
    assert plan.natural_speed_min == _MIN
    assert is_valid_duration_fit_plan(plan)


def test_validate_flags_empty_plan():
    plan = DurationFitPlan(
        id="p", localization_variant_id="v", decisions=[], created_at=_T0,
    )
    kinds = {i.kind for i in validate_duration_fit_plan(plan)}
    assert DurationFitIssueKind.EMPTY_PLAN in kinds


def test_validate_flags_extreme_speed_disguised_as_ok():
    # 手工构造：声称 OK_FITTED 却用 0.7x 极端压速 → 红线 EXTREME_SPEED
    plan = DurationFitPlan(
        id="p", localization_variant_id="v",
        decisions=[DurationFitDecision(
            sentence_id="a", estimated_ms=2100, target_ms=3000,
            fit_method=DurationFitStrategy.TTS_SPEED, final_ratio=0.7,
            status=DurationFitStatus.OK_FITTED, rationale="偷偷压速",
        )],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_duration_fit_plan(plan)}
    assert DurationFitIssueKind.EXTREME_SPEED in kinds


def test_validate_flags_status_method_inconsistency():
    plan = DurationFitPlan(
        id="p", localization_variant_id="v",
        decisions=[
            DurationFitDecision(
                sentence_id="a", estimated_ms=3000, target_ms=3000,
                fit_method=DurationFitStrategy.TTS_SPEED, final_ratio=1.0,
                status=DurationFitStatus.OK_UNCHANGED,  # UNCHANGED 不该带 method
                rationale="x",
            ),
            DurationFitDecision(
                sentence_id="b", estimated_ms=3100, target_ms=3000,
                fit_method=None, final_ratio=1.03,
                status=DurationFitStatus.OK_FITTED,  # FITTED 必须带 method
                rationale="y",
            ),
        ],
        created_at=_T0,
    )
    issues = validate_duration_fit_plan(plan)
    inconsistent = [
        i for i in issues
        if i.kind is DurationFitIssueKind.STATUS_METHOD_INCONSISTENT
    ]
    assert {i.ref for i in inconsistent} == {"a", "b"}


def test_validate_flags_review_without_reason():
    plan = DurationFitPlan(
        id="p", localization_variant_id="v",
        decisions=[DurationFitDecision(
            sentence_id="a", estimated_ms=6000, target_ms=3000,
            fit_method=DurationFitStrategy.BEAT_REPLAN, final_ratio=2.0,
            status=DurationFitStatus.NEEDS_REVIEW, rationale="x",
            review_reasons=[],  # 缺原因
        )],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_duration_fit_plan(plan)}
    assert DurationFitIssueKind.REVIEW_WITHOUT_REASON in kinds


def test_planner_output_always_passes_own_validate_fuzz():
    inputs = []
    for i, est in enumerate(range(500, 8001, 211)):
        inputs.append(_d(f"s{i}", estimated_ms=est, target_ms=3000,
                          broll_slack_ms=(i % 3) * 400, face_locked=(i % 2 == 0)))
    plan = plan_duration_fit(
        inputs, id="p", localization_variant_id="v", created_at=_T0,
    )
    assert validate_duration_fit_plan(plan) == []


# --- verifier 回归：两个曾 REFUTED 的反例 ----------------------------------

def test_regression_extremely_short_sentence_does_not_crash():
    # verifier A：est≪target 时 raw 舍入到 0 曾使合同 final_ratio>0 校验崩溃。
    # 现在应正常返回 NEEDS_REVIEW，且 final_ratio 仍 > 0。
    d = decide_duration_fit(_d("s", estimated_ms=1, target_ms=20001))
    assert d.status is DurationFitStatus.NEEDS_REVIEW
    assert d.final_ratio > 0.0
    # 成计划也不崩，且过自身护栏
    plan = plan_duration_fit(
        [_d("s0", estimated_ms=1, target_ms=100000)],
        id="p", localization_variant_id="v", created_at=_T0,
    )
    assert validate_duration_fit_plan(plan) == []


def test_regression_extreme_short_fuzz_no_crash_and_self_consistent():
    for target in (10000, 20001, 100000, 500000):
        for est in (1, 2, 5, 50):
            d = decide_duration_fit(_d("s", estimated_ms=est, target_ms=target))
            assert d.final_ratio > 0.0
            if d.status in (DurationFitStatus.OK_UNCHANGED,
                            DurationFitStatus.OK_FITTED):
                assert _MIN <= d.final_ratio <= _MAX


def test_regression_narrow_custom_band_stays_self_consistent():
    # verifier B：natural_min 比 unchanged 容差还窄时，step-0 曾产出超区间的
    # OK_UNCHANGED 并被自身护栏判 EXTREME_SPEED。现在应自洽。
    plan = plan_duration_fit(
        [_d("s", estimated_ms=985, target_ms=1000)],
        id="p", localization_variant_id="v", created_at=_T0,
        natural_min=0.99, natural_max=1.08,
    )
    assert validate_duration_fit_plan(plan) == []
    d = plan.decisions[0]
    if d.status in (DurationFitStatus.OK_UNCHANGED, DurationFitStatus.OK_FITTED):
        assert 0.99 <= d.final_ratio <= 1.08


def test_regression_narrow_band_fuzz_build_validate_consistent():
    for nmin in (0.90, 0.95, 0.99, 1.0):
        inputs = [
            _d(f"s{i}", estimated_ms=est, target_ms=1000)
            for i, est in enumerate(range(700, 1301, 23))
        ]
        plan = plan_duration_fit(
            inputs, id="p", localization_variant_id="v", created_at=_T0,
            natural_min=nmin, natural_max=1.08,
        )
        assert validate_duration_fit_plan(plan) == [], f"natural_min={nmin} 不自洽"
