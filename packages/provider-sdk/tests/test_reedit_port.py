"""句段判定端口：Unconfigured 诚实 + Fake 确定性/对齐 + 端到端过纯域重剪护栏。

端到端（provider-sdk 测试可依赖 domain 做验收，同 highlight/vlm/ocr 先例）：
Transcript → SegmentSpec → Fake.judge → build_reedit_plan → validate_reedit_plan == []。
"""

from datetime import UTC, datetime

from videoforge_contracts import (
    EditOpKind,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
)
from videoforge_domain import build_reedit_plan, validate_reedit_plan
from videoforge_provider_sdk import (
    FakeSegmentJudgeProvider,
    SegmentJudgeProvider,
    SegmentJudgeRequest,
    SegmentJudgeStatus,
    SegmentSpec,
    UnconfiguredSegmentJudgeProvider,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _transcript() -> Transcript:
    rows = [
        ("seg-0", 0, 4000, "大家好今天聊聊这颗新芯片"),
        ("seg-1", 4000, 4500, "嗯"),  # 口头禅 → filler
        ("seg-2", 4500, 9000, "实测能效比上一代提升四成"),
        ("seg-3", 9000, 13500, "实测能效比上一代提升四成"),  # 与上句重复 → repeat
        ("seg-4", 13500, 16000, "总结一下适合谁用"),
    ]
    return Transcript(
        id="tr", language="zh-CN", duration_ms=16000,
        segments=[TranscriptSegment(id=i, start_ms=a, end_ms=b, language="zh-CN",
                                    text=t, confidence=0.9) for i, a, b, t in rows],
        models=TranscriptModels(asr_provider="asr.x"), created_at=_T0,
    )


def _specs(tr: Transcript) -> list[SegmentSpec]:
    return [SegmentSpec(id=s.id, start_ms=s.start_ms, end_ms=s.end_ms, text=s.text)
            for s in tr.segments]


def test_protocol_conformance() -> None:
    assert isinstance(FakeSegmentJudgeProvider(), SegmentJudgeProvider)
    assert isinstance(UnconfiguredSegmentJudgeProvider(), SegmentJudgeProvider)


def test_unconfigured_is_honest() -> None:
    prov = UnconfiguredSegmentJudgeProvider()
    result = prov.judge(SegmentJudgeRequest(segments=_specs(_transcript())))
    assert result.status is SegmentJudgeStatus.UNCONFIGURED
    assert result.judgments == []  # 绝不静默造判定
    assert result.error_code is not None
    assert prov.health_check().status is SegmentJudgeStatus.UNCONFIGURED


def test_fake_deterministic_and_aligned() -> None:
    req = SegmentJudgeRequest(segments=_specs(_transcript()))
    fake = FakeSegmentJudgeProvider()
    a = fake.judge(req)
    b = fake.judge(req)
    assert a.ok and len(a.judgments) == 5  # 与句段一一对齐
    assert [j.model_dump() for j in a.judgments] == [j.model_dump() for j in b.judgments]


def test_fake_flags_filler_silence_repeat() -> None:
    specs = [
        SegmentSpec("s0", 0, 3000, "正常一句有信息"),
        SegmentSpec("s1", 3000, 3200, "嗯"),  # filler
        SegmentSpec("s2", 3200, 3400, "   "),  # 空白 → silence
        SegmentSpec("s3", 3400, 6000, "正常一句有信息"),  # 与 s0 重复
    ]
    js = {j.segment_id: j for j in FakeSegmentJudgeProvider().judge(
        SegmentJudgeRequest(segments=specs)).judgments}
    assert js["s0"].keep_recommended
    assert js["s1"].is_filler and not js["s1"].keep_recommended
    assert js["s2"].is_silence and not js["s2"].keep_recommended
    assert js["s3"].is_repeat and not js["s3"].keep_recommended


def test_end_to_end_transcript_to_valid_plan() -> None:
    tr = _transcript()
    result = FakeSegmentJudgeProvider().judge(SegmentJudgeRequest(segments=_specs(tr)))
    assert result.ok

    plan = build_reedit_plan(tr, result.judgments, plan_id="plan-e2e", created_at=_T0)
    kinds = [op.op for op in plan.ops]
    assert kinds == [EditOpKind.KEEP, EditOpKind.DELETE, EditOpKind.KEEP,
                     EditOpKind.DELETE, EditOpKind.KEEP]
    reasons = {op.reason for op in plan.ops if op.op == EditOpKind.DELETE}
    assert reasons == {"filler", "repeat"}
    # 两处删除各产生一个 jump cut，均有连续性说明
    assert len(plan.continuity) == 2
    # 核心验收：Fake 判定驱动的计划直接过纯域重剪护栏
    assert validate_reedit_plan(plan, transcript=tr) == []
    assert plan.kept_duration_ms == 4000 + 4500 + 2500  # seg-0 + seg-2 + seg-4
