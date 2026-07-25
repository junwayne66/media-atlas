"""热门片段：候选窗口不切句 + §5.2 加权评分可复现 + 重叠去重 + MMR 多样性 + Top-N。"""

from datetime import UTC, datetime

import pytest

from videoforge_contracts import (
    HighlightFeatures,
    HighlightReason,
    HighlightWeights,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
)
from videoforge_domain import (
    CandidateWindow,
    build_candidate_windows,
    derive_highlight_reasons,
    highlight_score,
    overlap_ratio,
    rank_highlights,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)
_WEIGHTS = HighlightWeights(template_version="highlight-v1")


def _transcript(spans: list[tuple[int, int]]) -> Transcript:
    return Transcript(
        id="tr",
        language="zh-CN",
        segments=[
            TranscriptSegment(
                id=f"seg-{i}",
                start_ms=a,
                end_ms=b,
                language="zh-CN",
                text=f"第{i}句内容承接上下文",
                confidence=0.9,
            )
            for i, (a, b) in enumerate(spans)
        ],
        models=TranscriptModels(asr_provider="asr.x"),
        created_at=_T0,
    )


def _feats(**over: float) -> HighlightFeatures:
    base = dict(
        hook_strength=0.5,
        self_containedness=0.5,
        information_density=0.5,
        surprise_or_conflict=0.5,
        emotional_energy=0.5,
        topic_relevance=0.5,
        visual_activity=0.5,
        speaker_prominence=0.5,
        ending_payoff=0.5,
        context_dependency=0.1,
        technical_defect=0.05,
    )
    base.update(over)
    return HighlightFeatures(**base)


# —— 候选窗口 ——


def test_windows_never_cut_a_sentence() -> None:
    spans = [(0, 5000), (5000, 10000), (10000, 15000), (15000, 20000), (20000, 25000)]
    tr = _transcript(spans)
    windows = build_candidate_windows(tr, min_ms=12000, max_ms=30000)
    starts = {a for a, _ in spans}
    ends = {b for _, b in spans}
    assert windows
    for w in windows:
        assert 12000 <= w.duration_ms <= 30000
        assert w.start_ms in starts and w.end_ms in ends  # 端点落在句子边界 → 不切句
    # 5 句 × 5s：3/4/5 句组合 = 3+2+1 = 6 个窗口
    assert len(windows) == 6


def test_windows_cover_included_segments_even_when_overlapping() -> None:
    # 回归：diarize 串话使片段重叠（seg-1 结束早于 seg-0）时，窗口仍须完整包住每个纳入句，不截断
    spans = [(0, 50000), (10000, 20000), (21000, 33000)]
    tr = _transcript(spans)
    id_span = {f"seg-{i}": s for i, s in enumerate(spans)}
    windows = build_candidate_windows(tr, min_ms=12000, max_ms=75000)
    assert windows
    for w in windows:
        for sid in w.segment_ids:
            a, b = id_span[sid]
            assert w.start_ms <= a and b <= w.end_ms  # 纳入句完整落在窗口内，未被截断


def test_single_oversized_sentence_yields_no_window() -> None:
    # 单句 90s、上限 75s：无法不切句地放入 → 不产窗口（诚实，不硬切）
    tr = _transcript([(0, 90000)])
    assert build_candidate_windows(tr, min_ms=12000, max_ms=75000) == []


def test_min_gt_max_rejected() -> None:
    with pytest.raises(ValueError, match="min_ms"):
        build_candidate_windows(_transcript([(0, 5000)]), min_ms=30000, max_ms=12000)


# —— 评分 ——


def test_highlight_score_matches_formula() -> None:
    # 9 正向项各 0.5（权重和 1.0）→ 0.5；惩罚 0.12*0.1 + 0.08*0.05 = 0.016 → 0.484
    score = highlight_score(_feats(), _WEIGHTS)
    assert abs(score - 0.484) < 1e-9


def test_score_reproducible_bit_identical() -> None:
    f = _feats(hook_strength=0.83, surprise_or_conflict=0.61)
    assert highlight_score(f, _WEIGHTS) == highlight_score(f, _WEIGHTS)


def test_penalty_terms_lower_score() -> None:
    clean = highlight_score(_feats(context_dependency=0.0, technical_defect=0.0), _WEIGHTS)
    penalized = highlight_score(_feats(context_dependency=0.9, technical_defect=0.9), _WEIGHTS)
    assert penalized < clean


def test_reason_codes_from_thresholds() -> None:
    reasons = set(
        derive_highlight_reasons(
            _feats(hook_strength=0.8, ending_payoff=0.7, information_density=0.7)
        )
    )
    assert HighlightReason.HOOK_QUOTE in reasons
    assert HighlightReason.CLEAR_PAYOFF in reasons
    assert HighlightReason.HIGH_INFO_DENSITY in reasons
    # 谨慎项：高上下文依赖被标注
    assert HighlightReason.CONTEXT_DEPENDENT in set(
        derive_highlight_reasons(_feats(context_dependency=0.8))
    )


# —— 去重 + MMR + Top-N ——


def _win(start: int, end: int, sid: str) -> CandidateWindow:
    return CandidateWindow(start_ms=start, end_ms=end, segment_ids=(sid,), text=f"{sid} 文本")


def test_overlap_ratio_containment_is_one() -> None:
    big = _win(0, 20000, "a")
    small = _win(2000, 8000, "b")  # 完全落入 big
    assert overlap_ratio(big, small) == 1.0


def test_dedup_drops_overlapping_lower_score() -> None:
    # 两个高度重叠窗口，只留高分者
    w_hi = _win(0, 20000, "hi")
    w_lo = _win(0, 18000, "lo")  # 与 w_hi 重叠 18000/18000 = 1.0
    w_far = _win(60000, 80000, "far")  # 不重叠
    features = [_feats(hook_strength=0.9), _feats(hook_strength=0.2), _feats(hook_strength=0.6)]
    result = rank_highlights(
        [w_hi, w_lo, w_far],
        features,
        weights=_WEIGHTS,
        top_n=5,
        id_prefix="hl",
        created_at=_T0,
    )
    kept = {c.start_ms for c in result.candidates}
    assert kept == {0, 60000}  # w_lo 被去重，w_hi + w_far 保留
    # 保留的是高分的 w_hi，不是 w_lo
    top = next(c for c in result.candidates if c.start_ms == 0)
    assert top.segment_ids == ["hi"]


def test_top_n_cap_and_ordering() -> None:
    wins = [_win(i * 30000, i * 30000 + 20000, f"s{i}") for i in range(6)]  # 互不重叠
    features = [_feats(hook_strength=0.1 * (i + 1)) for i in range(6)]  # 递增分数
    result = rank_highlights(
        wins,
        features,
        weights=_WEIGHTS,
        top_n=3,
        id_prefix="hl",
        created_at=_T0,
    )
    assert len(result.candidates) == 3  # Top-N 封顶
    assert result.candidates[0].id == "hl-0"
    # 首个是最高分（hook 0.6 的最后一个窗口）
    assert result.candidates[0].score == max(c.score for c in result.candidates)


def test_rank_is_deterministic() -> None:
    wins = [_win(i * 30000, i * 30000 + 20000, f"s{i}") for i in range(5)]
    features = [_feats(surprise_or_conflict=0.3 + 0.1 * i) for i in range(5)]
    kw = dict(weights=_WEIGHTS, top_n=4, id_prefix="hl", created_at=_T0)
    a = rank_highlights(wins, features, **kw)
    b = rank_highlights(wins, features, **kw)
    assert [(c.id, c.start_ms, c.score) for c in a.candidates] == [
        (c.id, c.start_ms, c.score) for c in b.candidates
    ]


def test_length_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="数量不一致"):
        rank_highlights(
            [_win(0, 20000, "a")], [], weights=_WEIGHTS, top_n=1, id_prefix="hl", created_at=_T0
        )


def test_empty_windows_yields_empty_set() -> None:
    result = rank_highlights([], [], weights=_WEIGHTS, top_n=5, id_prefix="hl", created_at=_T0)
    assert result.candidates == []
    assert result.weights_version == "highlight-v1"
