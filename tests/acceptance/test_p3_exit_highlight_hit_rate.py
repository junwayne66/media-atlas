"""P3 Exit 验收 —— Highlight Top-3 vs 人工标注命中率 ≥ 70%（§12 第 3 条）。

在 10 个中英转录 fixture 上：人工预先标注每条视频"应入选"的候选窗（HOOK/PAYOFF/HIGH_INFO）；
跑 rank_highlights Top-3；集合级命中率 ≥ 70%。

命中口径：Highlight 排序器的目标是"找到 highlight 所在的时间区域"，不是精确匹配人工
剪辑边界。因此采用「覆盖率」——人工标注区间被**某个** Top-3 窗口覆盖 ≥ 70%（|label ∩ win|
/ |label| ≥ 0.7）即视为命中；每人工标注最多计 1；跨 10 条 fixture 汇总命中率 ≥ 70%。

**证据边界**（诚实登记，verifier 指出）：
- 人工标注由本文件作者自拟（非独立测试者），Fake 特征打分是启发式（位置→hook/ending、
  文本长度→density）；因此本测试证的是"Fake + 作者标注综合命中率 ≥ 70%"，非"真实模型
  vs 独立标注 ≥ 70%"。真模型上线后需在此 fixture 上重跑。
- 集合级命中率允许某条 fixture 少命中被别条多命中抵消；下方额外断言"无一条 fixture 0/3"
  避免"数字合格但排序器彻底漏检某类内容"这一 vacuous 状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from videoforge_contracts import (
    HighlightWeights,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
)
from videoforge_domain import (
    build_candidate_windows,
    overlap_ratio,
    rank_highlights,
)
from videoforge_provider_sdk import (
    FakeHighlightFeatureProvider,
    HighlightFeatureRequest,
    HighlightWindowSpec,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)
_WEIGHTS = HighlightWeights(template_version="p3-exit-hl-v1")


@dataclass(frozen=True)
class LabelSpan:
    """人工标注：应入选的时间窗（该视频中的一个 highlight）。"""

    start_ms: int
    end_ms: int
    reason: str


@dataclass(frozen=True)
class HighlightFixture:
    """一条视频 fixture：转录 + 人工标注的应入选窗集合。"""

    video_id: str
    language: str
    duration_ms: int
    segments: list[tuple[int, int, str]]  # (start_ms, end_ms, text)
    labels: list[LabelSpan]


def _fixture(
    vid: str, language: str, segs: list[tuple[int, int, str]], labels: list[LabelSpan]
) -> HighlightFixture:
    return HighlightFixture(
        video_id=vid,
        language=language,
        duration_ms=max(e for _, e, _ in segs),
        segments=segs,
        labels=labels,
    )


# 10 条 fixture：每条 6~8 段，涵盖 zh/en 与 30~90s 时长；人工标注 3 个应入选窗
FIXTURES: list[HighlightFixture] = [
    _fixture(
        "v1-zh-tech",
        "zh-CN",
        [
            (0, 5000, "开场直接抛出一个反直觉结论"),
            (5000, 12000, "接着展开背景"),
            (12000, 22000, "关键数据放在这里"),
            (22000, 30000, "一个演示"),
            (30000, 38000, "对比失败案例"),
            (38000, 45000, "总结要点回到开场"),
            (45000, 50000, "call to action"),
        ],
        [
            LabelSpan(0, 12000, "HOOK"),
            LabelSpan(12000, 22000, "HIGH_INFO"),
            LabelSpan(38000, 50000, "PAYOFF"),
        ],
    ),
    _fixture(
        "v2-en-tech",
        "en-US",
        [
            (0, 6000, "here is the surprising claim"),
            (6000, 15000, "some context follows"),
            (15000, 25000, "the critical measurement"),
            (25000, 33000, "a demo of the effect"),
            (33000, 45000, "wrap up with the takeaway"),
        ],
        [
            LabelSpan(0, 15000, "HOOK"),
            LabelSpan(15000, 25000, "HIGH_INFO"),
            LabelSpan(33000, 45000, "PAYOFF"),
        ],
    ),
    _fixture(
        "v3-zh-recipe",
        "zh-CN",
        [
            (0, 8000, "这道菜有一个秘密"),
            (8000, 18000, "食材准备"),
            (18000, 28000, "关键火候在这一刻"),
            (28000, 40000, "装盘和最终口味"),
        ],
        [
            LabelSpan(0, 8000, "HOOK"),
            LabelSpan(18000, 28000, "HIGH_INFO"),
            LabelSpan(28000, 40000, "PAYOFF"),
        ],
    ),
    _fixture(
        "v4-en-fitness",
        "en-US",
        [
            (0, 7000, "this ten minute routine changes everything"),
            (7000, 20000, "warm up sequence"),
            (20000, 35000, "the core drill you must do"),
            (35000, 50000, "cool down and results"),
        ],
        [
            LabelSpan(0, 7000, "HOOK"),
            LabelSpan(20000, 35000, "HIGH_INFO"),
            LabelSpan(35000, 50000, "PAYOFF"),
        ],
    ),
    _fixture(
        "v5-zh-finance",
        "zh-CN",
        [
            (0, 6000, "先看结果 三年翻倍"),
            (6000, 15000, "方法很简单"),
            (15000, 27000, "关键在于三个动作"),
            (27000, 38000, "常见误区"),
            (38000, 48000, "长期视角总结"),
        ],
        [
            LabelSpan(0, 6000, "HOOK"),
            LabelSpan(15000, 27000, "HIGH_INFO"),
            LabelSpan(38000, 48000, "PAYOFF"),
        ],
    ),
    _fixture(
        "v6-en-travel",
        "en-US",
        [
            (0, 6000, "the best ramen shop is on this alley"),
            (6000, 18000, "how i found it"),
            (18000, 30000, "what to order and why"),
            (30000, 42000, "closing tips"),
        ],
        [
            LabelSpan(0, 6000, "HOOK"),
            LabelSpan(18000, 30000, "HIGH_INFO"),
            LabelSpan(30000, 42000, "PAYOFF"),
        ],
    ),
    _fixture(
        "v7-zh-photo",
        "zh-CN",
        [
            (0, 5000, "拍出电影感只需要一件事"),
            (5000, 15000, "器材背景"),
            (15000, 28000, "关键参数演示"),
            (28000, 40000, "回顾结果"),
        ],
        [
            LabelSpan(0, 5000, "HOOK"),
            LabelSpan(15000, 28000, "HIGH_INFO"),
            LabelSpan(28000, 40000, "PAYOFF"),
        ],
    ),
    _fixture(
        "v8-en-startup",
        "en-US",
        [
            (0, 8000, "we shipped v1 in six weeks and here is how"),
            (8000, 20000, "team setup"),
            (20000, 35000, "the three tools that made it possible"),
            (35000, 50000, "lessons learned"),
        ],
        [
            LabelSpan(0, 8000, "HOOK"),
            LabelSpan(20000, 35000, "HIGH_INFO"),
            LabelSpan(35000, 50000, "PAYOFF"),
        ],
    ),
    _fixture(
        "v9-zh-ai",
        "zh-CN",
        [
            (0, 6000, "端侧推理 20ms 是怎么做到的"),
            (6000, 15000, "系统架构"),
            (15000, 28000, "关键优化点"),
            (28000, 40000, "对比基线"),
            (40000, 50000, "结论与未来方向"),
        ],
        [
            LabelSpan(0, 6000, "HOOK"),
            LabelSpan(15000, 28000, "HIGH_INFO"),
            LabelSpan(40000, 50000, "PAYOFF"),
        ],
    ),
    _fixture(
        "v10-en-ai",
        "en-US",
        [
            (0, 7000, "our on device model beats gpt-4 on math"),
            (7000, 18000, "the training data"),
            (18000, 32000, "the crucial architecture change"),
            (32000, 45000, "benchmark numbers and caveats"),
        ],
        [
            LabelSpan(0, 7000, "HOOK"),
            LabelSpan(18000, 32000, "HIGH_INFO"),
            LabelSpan(32000, 45000, "PAYOFF"),
        ],
    ),
]


def _to_transcript(fx: HighlightFixture) -> Transcript:
    segs = [
        TranscriptSegment(
            id=f"{fx.video_id}-seg-{i}",
            start_ms=s,
            end_ms=e,
            language=fx.language,
            text=t,
            confidence=0.9,
        )
        for i, (s, e, t) in enumerate(fx.segments)
    ]
    return Transcript(
        id=f"tr-{fx.video_id}",
        language=fx.language,
        duration_ms=fx.duration_ms,
        segments=segs,
        models=TranscriptModels(asr_provider="fake"),
        created_at=_T0,
    )


def _coverage(label_start: int, label_end: int, win_start: int, win_end: int) -> float:
    """人工标注被某 Top-3 窗覆盖的比例：|label ∩ win| / |label|。"""
    inter = max(0, min(label_end, win_end) - max(label_start, win_start))
    lab_len = label_end - label_start
    return inter / lab_len if lab_len > 0 else 0.0


def _top3_for(fx: HighlightFixture) -> list[tuple[int, int]]:
    tr = _to_transcript(fx)
    windows = build_candidate_windows(tr, min_ms=5000, max_ms=min(30000, fx.duration_ms))
    if not windows:
        return []
    specs = [
        HighlightWindowSpec(
            start_ms=w.start_ms,
            end_ms=w.end_ms,
            text=w.text,
            index_in_video=i,
            total_windows=len(windows),
        )
        for i, w in enumerate(windows)
    ]
    feats = FakeHighlightFeatureProvider().score(
        HighlightFeatureRequest(windows=specs, video_duration_ms=fx.duration_ms)
    )
    hl = rank_highlights(
        windows,
        feats.features,
        weights=_WEIGHTS,
        top_n=3,
        id_prefix=f"hl-{fx.video_id}",
        created_at=_T0,
        source_transcript_id=tr.id,
        feature_provider="fake",
    )
    return [(c.start_ms, c.end_ms) for c in hl.candidates]


def _hits(
    top3: list[tuple[int, int]], labels: list[LabelSpan], coverage_threshold: float = 0.7
) -> int:
    """人工标注被某 Top-3 窗覆盖 ≥ 阈值 → 计一命中；每人工标注最多计 1（不重复）。"""
    hits = 0
    for lab in labels:
        for s, e in top3:
            if _coverage(lab.start_ms, lab.end_ms, s, e) >= coverage_threshold:
                hits += 1
                break
    return hits


def test_highlight_top3_hit_rate_ge_70_percent() -> None:
    """§12: Top-3 vs 人工标注命中率 ≥ 70%（十条 fixture 集合级 + 每条至少 1 命中）。"""
    total_labels = 0
    total_hits = 0
    per_fixture: dict[str, tuple[int, int, list]] = {}
    zero_hit_fixtures: list[str] = []
    for fx in FIXTURES:
        top3 = _top3_for(fx)
        h = _hits(top3, fx.labels)
        per_fixture[fx.video_id] = (h, len(fx.labels), top3)
        total_hits += h
        total_labels += len(fx.labels)
        if h == 0:
            zero_hit_fixtures.append(fx.video_id)
    rate = total_hits / total_labels if total_labels else 0.0
    detail = "; ".join(f"{k}={v[0]}/{v[1]}" for k, v in per_fixture.items())
    # 集合级 ≥ 70%
    assert rate >= 0.70, f"Top-3 命中率 {rate:.1%} < 70%。明细: {detail}"
    # 无一条 fixture 完全漏检（防"数字合格但整类内容漏检"的 vacuous 状态）
    assert not zero_hit_fixtures, (
        f"以下 fixture Top-3 完全未命中人工标注：{zero_hit_fixtures}。明细: {detail}"
    )


def test_overlap_ratio_symmetric_on_containment() -> None:
    """辅助：完全包含 → overlap_ratio == 1.0（保 rank_highlights 去重语义可信）。"""
    from videoforge_domain.highlight import CandidateWindow

    a = CandidateWindow(start_ms=0, end_ms=5000, segment_ids=("s0",), text="x")
    b = CandidateWindow(start_ms=1000, end_ms=3000, segment_ids=("s1",), text="y")
    assert overlap_ratio(a, b) == 1.0
    assert overlap_ratio(b, a) == 1.0
