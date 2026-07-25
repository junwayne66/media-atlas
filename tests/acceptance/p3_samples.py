"""P3 Exit 验收样本：20 个中英/AI/非-AI 主题 × 两模式共 Blueprint 端到端可跑。

每样本是一个"最小可跑单元"——VideoBlueprint + ClaimTable 已构造，
downstream 的 Script/Highlight/AssetPlan/CreativeTimeline/QA/Exporter 全由 domain
在测试中即时组装。这里只提供 Blueprint 参数，避免固化下游脆弱数据。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from videoforge_contracts import (
    Claim,
    ClaimSourceStatus,
    EvidenceSpan,
    RhetoricalBeat,
    RhetoricalBeatKind,
    VideoBlueprint,
    VisualBeat,
    VisualBeatKind,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


@dataclass(frozen=True)
class P3Sample:
    """一个验收样本：id + 语言 + 主题类别 + 目标时长 + 蓝图。"""

    id: str
    language: str
    category: str  # ai / non-ai
    duration_target_ms: int
    blueprint: VideoBlueprint


def _bp(
    sid: str,
    dur_ms: int,
    beats: list[tuple[str, int, int, str]],
    claims: list[tuple[str, str, ClaimSourceStatus]],
) -> VideoBlueprint:
    """构造 blueprint：beats 是 [(kind, start, end, summary)]；claims 是 [(id, text, status)]。"""
    rhet = [
        RhetoricalBeat(
            id=f"{sid}-r{i}", kind=RhetoricalBeatKind(k), start_ms=s, end_ms=e, summary=summary
        )
        for i, (k, s, e, summary) in enumerate(beats)
    ]
    cs = [
        Claim(
            id=cid,
            text=text,
            source_status=status,
            evidence=[
                EvidenceSpan(kind="transcript", ref_id=f"{sid}-seg-0", start_ms=0, end_ms=2000)
            ],
        )
        for cid, text, status in claims
    ]
    return VideoBlueprint(
        id=f"bp-{sid}",
        source_artifact_id=f"art-{sid}",
        duration_ms=dur_ms,
        claims=cs,
        rhetorical_beats=rhet,
        visual_beats=[
            VisualBeat(id=f"{sid}-v0", kind=VisualBeatKind.PERSON, start_ms=0, end_ms=dur_ms // 2),
            VisualBeat(
                id=f"{sid}-v1",
                kind=VisualBeatKind.SCREEN_RECORD,
                start_ms=dur_ms // 2,
                end_ms=dur_ms,
            ),
        ],
        coverage=1.0,
        fusion_provider="fake",
        created_at=_T0,
    )


def _standard_beats(dur_ms: int) -> list[tuple[str, int, int, str]]:
    q1, q2, q3 = dur_ms // 4, dur_ms // 2, dur_ms * 3 // 4
    return [
        ("HOOK", 0, q1, "开场钩子"),
        ("EVIDENCE", q1, q2, "证据展示"),
        ("DEMO", q2, q3, "演示"),
        ("CONCLUSION", q3, dur_ms, "结论"),
    ]


# 20 样本：AI 与非-AI 各半，中英各半，覆盖各时长
_ZH_TOPICS = [
    ("ai-chip", "该芯片实测能效比上一代提升四成", ClaimSourceStatus.VERIFIED),
    ("ai-inference", "端侧推理时延降低到 20ms", ClaimSourceStatus.VERIFIED),
    ("ai-agent", "多智能体框架并行度提升三倍", ClaimSourceStatus.UNVERIFIED),
    ("ai-training", "训练成本比 GPT-4 降低 80 percent", ClaimSourceStatus.DISPUTED),
    ("ai-privacy", "本地模型不上传用户数据", ClaimSourceStatus.VERIFIED),
    ("food-recipe", "这道菜的关键在于火候", ClaimSourceStatus.OPINION),
    ("travel-diary", "东京最好的拉面店在这里", ClaimSourceStatus.OPINION),
    ("fitness", "每天 20 分钟核心训练", ClaimSourceStatus.OPINION),
    ("finance", "指数基金定投三年翻倍", ClaimSourceStatus.UNVERIFIED),
    ("photography", "光圈越小景深越深", ClaimSourceStatus.VERIFIED),
]
_EN_TOPICS = [
    ("ai-agent-en", "the framework handles 10k concurrent agents", ClaimSourceStatus.UNVERIFIED),
    ("ai-model-en", "the model runs on device with 2GB RAM", ClaimSourceStatus.VERIFIED),
    ("ai-startup-en", "we shipped v1 in six weeks", ClaimSourceStatus.VERIFIED),
    ("ai-tools-en", "cursor auto-completion is 40 percent faster", ClaimSourceStatus.UNVERIFIED),
    ("ai-benchmarks-en", "our model beats gpt-4 on math", ClaimSourceStatus.DISPUTED),
    ("coffee-en", "cold brew requires 12 hours", ClaimSourceStatus.OPINION),
    ("running-en", "zone 2 training builds base", ClaimSourceStatus.OPINION),
    ("keyboard-en", "topre switches feel unique", ClaimSourceStatus.OPINION),
    ("cars-en", "the ev range dropped 30 percent in winter", ClaimSourceStatus.VERIFIED),
    ("gardening-en", "morning watering reduces evaporation", ClaimSourceStatus.VERIFIED),
]

DURATIONS = [30000, 45000, 60000, 90000]


def build_samples() -> list[P3Sample]:
    samples: list[P3Sample] = []
    for i, (topic, text, status) in enumerate(_ZH_TOPICS):
        dur = DURATIONS[i % len(DURATIONS)]
        cat = "ai" if topic.startswith("ai-") else "non-ai"
        samples.append(
            P3Sample(
                id=f"zh-{topic}",
                language="zh-CN",
                category=cat,
                duration_target_ms=dur,
                blueprint=_bp(topic, dur, _standard_beats(dur), [(f"c-{topic}-0", text, status)]),
            )
        )
    for i, (topic, text, status) in enumerate(_EN_TOPICS):
        dur = DURATIONS[i % len(DURATIONS)]
        cat = "ai" if topic.startswith("ai-") else "non-ai"
        samples.append(
            P3Sample(
                id=f"en-{topic}",
                language="en-US",
                category=cat,
                duration_target_ms=dur,
                blueprint=_bp(topic, dur, _standard_beats(dur), [(f"c-{topic}-0", text, status)]),
            )
        )
    return samples


SAMPLES = build_samples()
