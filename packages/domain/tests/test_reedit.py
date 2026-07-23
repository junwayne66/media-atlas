"""原片重剪：规划器（保留/删除/重排 + jump cut 连续性）+ §4.2 护栏。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    ContinuityRuleKind,
    EditOp,
    EditOpKind,
    ReeditPlan,
    ReframeFollow,
    ReframeHint,
    SegmentJudgment,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
)
from videoforge_domain import (
    ReeditIssueKind,
    build_reedit_plan,
    is_valid_reedit_plan,
    validate_reedit_plan,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _transcript(spans: list[tuple[int, int]], *, duration: int | None = None) -> Transcript:
    return Transcript(
        id="tr", language="zh-CN",
        duration_ms=duration,
        segments=[
            TranscriptSegment(id=f"seg-{i}", start_ms=a, end_ms=b, language="zh-CN",
                              text=f"第{i}句", confidence=0.9)
            for i, (a, b) in enumerate(spans)
        ],
        models=TranscriptModels(asr_provider="asr.x"), created_at=_T0,
    )


def _judge(sid: str, *, keep: bool = True, **flags: bool) -> SegmentJudgment:
    return SegmentJudgment(segment_id=sid, keep_recommended=keep, **flags)


# —— 规划器 ——

def test_build_plan_keep_delete_reorder_and_continuity() -> None:
    tr = _transcript([(0, 5000), (5000, 6000), (6000, 11000), (11000, 16000)], duration=16000)
    judgments = [
        _judge("seg-0"), _judge("seg-1", keep=False, is_filler=True),
        _judge("seg-2"), _judge("seg-3"),
    ]
    plan = build_reedit_plan(
        tr, judgments, plan_id="plan-0", created_at=_T0,
        reframe=ReframeHint(target_aspect_ratio="9:16", follow=ReframeFollow.SPEAKER),
    )
    kinds = [op.op for op in plan.ops]
    assert kinds == [EditOpKind.KEEP, EditOpKind.DELETE, EditOpKind.KEEP, EditOpKind.KEEP]
    keeps = [op for op in plan.ops if op.op == EditOpKind.KEEP]
    assert [op.output_order for op in keeps] == [0, 1, 2]  # 保留段按源序编号
    assert plan.kept_duration_ms == 15000  # 5000+5000+5000
    assert all(op.reframe is not None for op in keeps)  # 每 KEEP 附重构图建议
    # 删除 seg-1 后 seg-0→seg-2 相邻 → 一处 jump cut 平滑说明
    assert len(plan.continuity) == 1
    assert plan.continuity[0].kind is ContinuityRuleKind.JUMPCUT_SMOOTH
    assert plan.continuity[0].at_ms == 5000
    assert validate_reedit_plan(plan, transcript=tr) == []  # 自产计划过护栏


def test_delete_reason_from_flags() -> None:
    tr = _transcript([(0, 5000), (5000, 5500), (5500, 10000)], duration=10000)
    plan = build_reedit_plan(
        tr, [_judge("seg-0"), _judge("seg-1", keep=False, is_silence=True), _judge("seg-2")],
        plan_id="p", created_at=_T0,
    )
    delete = next(op for op in plan.ops if op.op == EditOpKind.DELETE)
    assert delete.reason == "silence"


def test_build_merges_overlapping_segments_or_semantics() -> None:
    # 回归：diarize 串话使片段重叠。自产计划不得产 KEEP_OVERLAP，也不得双计 kept_duration。
    # OR 语义：只要簇内任一片段保留即整簇 KEEP（保守，避免切走同时正说话的另一路）。
    tr = _transcript([(0, 10000), (3000, 6000)], duration=10000)
    plan = build_reedit_plan(tr, [], plan_id="p", created_at=_T0)  # 都默认保留
    assert len(plan.ops) == 1  # 两段合成一簇一 KEEP
    assert plan.ops[0].op is EditOpKind.KEEP
    assert plan.ops[0].source_start_ms == 0 and plan.ops[0].source_end_ms == 10000
    assert set(plan.ops[0].segment_ids) == {"seg-0", "seg-1"}
    assert plan.kept_duration_ms == 10000  # 未双计
    assert validate_reedit_plan(plan, transcript=tr) == []


def test_build_valid_when_duration_less_than_last_segment() -> None:
    # 回归：合同不校验 duration_ms 与段边界一致；自产计划不得因申报 duration 偏小而误报越界。
    tr = _transcript([(0, 5000)], duration=3000)
    plan = build_reedit_plan(tr, [], plan_id="p", created_at=_T0)
    assert validate_reedit_plan(plan, transcript=tr) == []


def test_mid_sentence_cut_flagged_under_overlap() -> None:
    # 回归：手工/未来 LLM 计划中，端点即便在扁平边界集里，但严格落入某段内部仍属切句。
    tr = _transcript([(0, 10000), (3000, 6000)], duration=10000)
    bad = _plan([_keep("op-0", 0, 6000, 0)])  # 6000 在 ends 集里，但严格落入 seg-0 内部
    kinds = {i.kind for i in validate_reedit_plan(bad, transcript=tr)}
    assert ReeditIssueKind.MID_SENTENCE_CUT in kinds


def test_no_judgment_defaults_keep() -> None:
    tr = _transcript([(0, 5000), (5000, 10000)], duration=10000)
    plan = build_reedit_plan(tr, [], plan_id="p", created_at=_T0)  # 无判定
    assert all(op.op == EditOpKind.KEEP for op in plan.ops)
    assert plan.kept_duration_ms == 10000


# —— 护栏 ——

def _keep(oid: str, a: int, b: int, order: int) -> EditOp:
    return EditOp(id=oid, op=EditOpKind.KEEP, source_start_ms=a, source_end_ms=b,
                  segment_ids=[], output_order=order)


def _plan(ops: list[EditOp], continuity=()) -> ReeditPlan:
    return ReeditPlan(id="pl", ops=ops, continuity=list(continuity),
                      kept_duration_ms=0, created_at=_T0)


def test_empty_plan_flagged() -> None:
    tr = _transcript([(0, 5000)], duration=5000)
    kinds = {i.kind for i in validate_reedit_plan(_plan([]), transcript=tr)}
    assert ReeditIssueKind.EMPTY_PLAN in kinds


def test_mid_sentence_cut_flagged() -> None:
    tr = _transcript([(0, 5000), (5000, 10000)], duration=10000)
    # 结束 3000 不在任何句子边界 → 切句
    bad = _plan([_keep("op-0", 0, 3000, 0)])
    kinds = {i.kind for i in validate_reedit_plan(bad, transcript=tr)}
    assert ReeditIssueKind.MID_SENTENCE_CUT in kinds


def test_range_out_of_bounds_flagged() -> None:
    tr = _transcript([(0, 5000)], duration=5000)
    bad = _plan([_keep("op-0", 0, 5000, 0),
                 EditOp(id="op-1", op=EditOpKind.KEEP, source_start_ms=5000, source_end_ms=9000,
                        output_order=1)])
    kinds = {i.kind for i in validate_reedit_plan(bad, transcript=tr)}
    assert ReeditIssueKind.RANGE_OUT_OF_BOUNDS in kinds


def test_speed_out_of_range_flagged() -> None:
    tr = _transcript([(0, 5000), (5000, 10000)], duration=10000)
    bad = _plan([EditOp(id="op-0", op=EditOpKind.SPEED, source_start_ms=0, source_end_ms=5000,
                        speed=5.0)])
    kinds = {i.kind for i in validate_reedit_plan(bad, transcript=tr)}
    assert ReeditIssueKind.SPEED_OUT_OF_RANGE in kinds


def test_keep_overlap_flagged() -> None:
    tr = _transcript([(0, 5000), (5000, 10000)], duration=10000)
    bad = _plan([_keep("op-0", 0, 10000, 0), _keep("op-1", 5000, 10000, 1)])  # 重叠
    kinds = {i.kind for i in validate_reedit_plan(bad, transcript=tr)}
    assert ReeditIssueKind.KEEP_OVERLAP in kinds


def test_invalid_output_order_flagged() -> None:
    tr = _transcript([(0, 5000), (5000, 10000)], duration=10000)
    bad = _plan([_keep("op-0", 0, 5000, 0), _keep("op-1", 5000, 10000, 0)])  # 重复 order
    kinds = {i.kind for i in validate_reedit_plan(bad, transcript=tr)}
    assert ReeditIssueKind.INVALID_OUTPUT_ORDER in kinds


def test_unhandled_jumpcut_flagged() -> None:
    tr = _transcript([(0, 5000), (5000, 6000), (6000, 10000)], duration=10000)
    # 保留 seg-0 与 seg-2，中间 seg-1 被删但没有连续性说明 → jump cut 未处理
    bad = _plan([_keep("op-0", 0, 5000, 0), _keep("op-2", 6000, 10000, 1)])
    kinds = {i.kind for i in validate_reedit_plan(bad, transcript=tr)}
    assert ReeditIssueKind.UNHANDLED_JUMPCUT in kinds
    assert not is_valid_reedit_plan(bad, transcript=tr)
