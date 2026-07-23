"""原片重剪规划（docs/modules/42 §4）。纯函数，可复现。

- build_reedit_plan：源转录 + 逐句判定（SegmentJudgment）→ 有序 EditOp（保留/删除）+ 连续性说明。
  删静音/口头禅/重复/低信息段，保留段按源序编 output_order，逐 KEEP 附 REFRAME 建议；删除段夹在
  两个保留段之间会产生 jump cut，自动标 JUMPCUT_SMOOTH（§4.2）。
- validate_reedit_plan：§4.2 护栏——操作边界不切句（落在句子边界）、KEEP 覆盖不重叠、output_order
  为 0..k-1 排列、SPEED 倍率在允许区间、每处 jump cut 都有连续性处理 → typed ReeditIssue。

低信息/填充判定本身是模型判断（provider 产出 SegmentJudgment）；本模块只据判定成计划并施护栏。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    ContinuityNote,
    ContinuityRuleKind,
    EditOp,
    EditOpKind,
    ReeditPlan,
    ReframeHint,
    SegmentJudgment,
    Transcript,
)

_DEFAULT_SPEED_RANGE = (0.5, 2.0)  # 允许变速区间（§4.1：变速只在允许区间）
# 连续性处理里能"接住"一个 jump cut 的手法
_JUMPCUT_HANDLERS = frozenset(
    {
        ContinuityRuleKind.JUMPCUT_SMOOTH,
        ContinuityRuleKind.INSERT_BROLL,
        ContinuityRuleKind.J_CUT,
        ContinuityRuleKind.L_CUT,
    }
)


def _drop_reason(j: SegmentJudgment) -> str:
    if j.is_silence:
        return "silence"
    if j.is_filler:
        return "filler"
    if j.is_repeat:
        return "repeat"
    if j.is_low_info:
        return "low_info"
    return j.note or "dropped"


def build_reedit_plan(
    transcript: Transcript,
    judgments: list[SegmentJudgment],
    *,
    plan_id: str,
    created_at: datetime,
    source_asset_id: str | None = None,
    reframe: ReframeHint | None = None,
) -> ReeditPlan:
    """源转录 + 逐句判定 → ReeditPlan（保留/删除有序操作 + jump cut 连续性说明）。

    重叠感知：diarize 串话会让转录出现重叠片段（合同合法），无法只切走其中一段而不动另一段。
    故先按 cover_end 把重叠或严格相接内的片段合并成"簇"，每簇一个 EditOp；簇内采 OR 语义
    ——只要任一片段保留即整簇 KEEP（保守，避免切走同时正在说话的另一路），全簇皆删才 DELETE。
    """
    judged = {j.segment_id: j for j in judgments}
    segs = sorted(transcript.segments, key=lambda s: (s.start_ms, s.end_ms))

    # 聚簇：seg.start < 当前簇 cover_end 即并入（严格相接 a.end==b.start 属新簇，输出连续）
    clusters: list[tuple[int, int, list[str], list[SegmentJudgment | None]]] = []
    cur_start: int | None = None
    cur_end = 0
    cur_ids: list[str] = []
    cur_j: list[SegmentJudgment | None] = []
    for seg in segs:
        if cur_start is None or seg.start_ms >= cur_end:
            if cur_start is not None:
                clusters.append((cur_start, cur_end, cur_ids, cur_j))
            cur_start, cur_end = seg.start_ms, seg.end_ms
            cur_ids, cur_j = [seg.id], [judged.get(seg.id)]
        else:
            cur_end = max(cur_end, seg.end_ms)  # cover_end：包住整簇最远 end
            cur_ids.append(seg.id)
            cur_j.append(judged.get(seg.id))
    if cur_start is not None:
        clusters.append((cur_start, cur_end, cur_ids, cur_j))

    ops: list[EditOp] = []
    kept_spans: list[tuple[int, int]] = []
    kept_duration = 0
    order = 0
    for i, (start, end, seg_ids, js) in enumerate(clusters):
        # OR 语义：任一片段建议保留即整簇 KEEP；无判定 == 默认保留
        keep_any = any((j is None) or j.keep_recommended for j in js)
        if keep_any:
            ops.append(
                EditOp(
                    id=f"op-{i}", op=EditOpKind.KEEP, source_start_ms=start,
                    source_end_ms=end, segment_ids=list(seg_ids), output_order=order,
                    reframe=reframe,
                )
            )
            kept_spans.append((start, end))
            kept_duration += end - start
            order += 1
        else:
            # 全簇皆删：按优先级取一个删除原因
            drop = next((_drop_reason(j) for j in js if j is not None), "dropped")
            ops.append(
                EditOp(
                    id=f"op-{i}", op=EditOpKind.DELETE, source_start_ms=start,
                    source_end_ms=end, segment_ids=list(seg_ids), reason=drop,
                )
            )

    # 连续性：输出里相邻的两个保留段在源上不接（源段被删或存在自然空隙）→ jump cut，标平滑。
    # 文案不臆测原因，因为空隙可能来自删除，也可能来自源本身。
    continuity: list[ContinuityNote] = []
    for (_a_start, a_end), (b_start, _b_end) in zip(kept_spans, kept_spans[1:], strict=False):
        if b_start > a_end:
            continuity.append(
                ContinuityNote(
                    kind=ContinuityRuleKind.JUMPCUT_SMOOTH, at_ms=a_end,
                    detail=f"[{a_end},{b_start}) 处输出不连续，用推拉/构图变化平滑",
                )
            )

    return ReeditPlan(
        id=plan_id,
        source_transcript_id=transcript.id,
        source_asset_id=source_asset_id,
        ops=ops,
        continuity=continuity,
        kept_duration_ms=kept_duration,
        created_at=created_at,
    )


class ReeditIssueKind(StrEnum):
    EMPTY_PLAN = "EMPTY_PLAN"
    MID_SENTENCE_CUT = "MID_SENTENCE_CUT"
    RANGE_OUT_OF_BOUNDS = "RANGE_OUT_OF_BOUNDS"
    KEEP_OVERLAP = "KEEP_OVERLAP"
    INVALID_OUTPUT_ORDER = "INVALID_OUTPUT_ORDER"
    SPEED_OUT_OF_RANGE = "SPEED_OUT_OF_RANGE"
    UNHANDLED_JUMPCUT = "UNHANDLED_JUMPCUT"


@dataclass(frozen=True)
class ReeditIssue:
    kind: ReeditIssueKind
    ref: str
    detail: str


def validate_reedit_plan(
    plan: ReeditPlan,
    *,
    transcript: Transcript,
    speed_range: tuple[float, float] = _DEFAULT_SPEED_RANGE,
) -> list[ReeditIssue]:
    """§4.2 护栏；返回全部违规（空 = 通过）。"""
    issues: list[ReeditIssue] = []
    if not plan.ops:
        issues.append(ReeditIssue(ReeditIssueKind.EMPTY_PLAN, plan.id, "计划无操作"))
        return issues

    # 时长上限：max(申报 duration_ms, 实际最远段 end)——duration_ms 与段边界都是合同合法输入，
    # 二者可能不一致（合同不做跨段一致性校验），此处以"实际可达最远时间"为准，避免自产计划误判越界。
    max_seg_end = max((s.end_ms for s in transcript.segments), default=0)
    duration = max(transcript.duration_ms or 0, max_seg_end)
    seg_starts = {s.start_ms for s in transcript.segments}
    seg_ends = {s.end_ms for s in transcript.segments}
    lo, hi = speed_range

    def _falls_inside_segment(t: int) -> bool:
        # 严格落入某段内部即切句，即便端点也在其他段的边界集里
        return any(s.start_ms < t < s.end_ms for s in transcript.segments)

    for op in plan.ops:
        if op.source_start_ms < 0 or op.source_end_ms > duration:
            issues.append(
                ReeditIssue(ReeditIssueKind.RANGE_OUT_OF_BOUNDS, op.id,
                            f"[{op.source_start_ms},{op.source_end_ms}] 超出 [0,{duration}]")
            )
        # 边界须落在句子边界；重叠片段下"落在某段边界"还不够，还须不切另一段的内部（§4.2）
        boundary_ok = (
            op.source_start_ms in seg_starts and op.source_end_ms in seg_ends
            and not _falls_inside_segment(op.source_start_ms)
            and not _falls_inside_segment(op.source_end_ms)
        )
        if not boundary_ok:
            issues.append(
                ReeditIssue(ReeditIssueKind.MID_SENTENCE_CUT, op.id, "操作边界不在句子边界")
            )
        if op.op == EditOpKind.SPEED and (op.speed is None or not (lo <= op.speed <= hi)):
            issues.append(
                ReeditIssue(ReeditIssueKind.SPEED_OUT_OF_RANGE, op.id,
                            f"倍率 {op.speed} 不在允许区间 [{lo},{hi}]")
            )

    keeps = [op for op in plan.ops if op.op == EditOpKind.KEEP]
    orders = [op.output_order for op in keeps]
    if any(o is None for o in orders) or sorted(o for o in orders if o is not None) != list(
        range(len(keeps))
    ):
        issues.append(
            ReeditIssue(ReeditIssueKind.INVALID_OUTPUT_ORDER, plan.id,
                        f"KEEP 的 output_order 应为 0..{len(keeps) - 1} 的排列")
        )

    by_src = sorted(keeps, key=lambda o: o.source_start_ms)
    for a, b in zip(by_src, by_src[1:], strict=False):
        if b.source_start_ms < a.source_end_ms:
            issues.append(
                ReeditIssue(ReeditIssueKind.KEEP_OVERLAP, b.id,
                            f"KEEP 源区间与 {a.id} 重叠")
            )

    # 每处 jump cut（保留段间有被删空隙）都须有连续性处理
    handled = {n.at_ms for n in plan.continuity if n.kind in _JUMPCUT_HANDLERS}
    for a, b in zip(by_src, by_src[1:], strict=False):
        if b.source_start_ms > a.source_end_ms and a.source_end_ms not in handled:
            issues.append(
                ReeditIssue(ReeditIssueKind.UNHANDLED_JUMPCUT, a.id,
                            f"{a.source_end_ms}ms 处 jump cut 无连续性处理")
            )
    return issues


def is_valid_reedit_plan(plan: ReeditPlan, **kwargs) -> bool:
    return not validate_reedit_plan(plan, **kwargs)
