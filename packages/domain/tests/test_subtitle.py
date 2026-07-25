"""VF-402 字幕引擎 domain 测试：分段/CPS/多格式渲染/校验护栏。"""

from datetime import UTC, datetime

import pytest

from videoforge_contracts import (
    SafeAreaSpec,
    SubtitleCue,
    SubtitleFormat,
    SubtitleLine,
    SubtitleStyleHint,
    SubtitleTemplate,
    SubtitleTrack,
    SubtitleWord,
)
from videoforge_domain import (
    SubtitleIssueKind,
    is_valid_subtitle_track,
    pack_lines_into_cue,
    render,
    render_ass,
    render_srt,
    segment_text_into_lines,
    to_timeline_overlay,
    validate_subtitle_track,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _zh_tpl(**overrides) -> SubtitleTemplate:
    defaults = dict(
        id="tpl",
        language="zh-CN",
        max_chars_per_line=16,
        max_lines_per_cue=2,
        cjk_chars_per_sec=8.0,
        min_cue_duration_ms=500,
        max_cue_duration_ms=6000,
        created_at=_T0,
    )
    defaults.update(overrides)
    return SubtitleTemplate(**defaults)


def _en_tpl(**overrides) -> SubtitleTemplate:
    defaults = dict(
        id="tpl-en",
        language="en-US",
        max_chars_per_line=42,
        max_lines_per_cue=2,
        en_chars_per_sec=17.0,
        en_words_per_sec=3.5,
        min_cue_duration_ms=500,
        max_cue_duration_ms=6000,
        created_at=_T0,
    )
    defaults.update(overrides)
    return SubtitleTemplate(**defaults)


# —— 分段 ——


def test_segment_cjk_by_char_length() -> None:
    text = "这是一段较长的中文测试字幕文字"
    lines = segment_text_into_lines(text, template=_zh_tpl(max_chars_per_line=8))
    assert all(len(line) <= 8 for line in lines)
    assert "".join(lines) == text.strip()


def test_segment_en_by_word_boundary() -> None:
    lines = segment_text_into_lines(
        "the quick brown fox jumps over the lazy dog",
        template=_en_tpl(max_chars_per_line=20),
    )
    for line in lines:
        assert len(line) <= 20
    assert " ".join(lines) == "the quick brown fox jumps over the lazy dog"


def test_segment_protects_number_unit() -> None:
    """数字+单位不该被切开（§5.1）。8 字上限、'20 ms' 是保护块。"""
    text = "端侧推理仅需 20 ms 完成"
    lines = segment_text_into_lines(text, template=_zh_tpl(max_chars_per_line=8))
    # "20 ms" 应完整出现在某一行里
    assert any("20 ms" in line for line in lines)


def test_segment_protects_number_unit_adjacent_cjk() -> None:
    """verifier REFUTED：'20 ms结束' 单位后紧跟 CJK 时，\\b 不成立、首版保护失效。
    修 `(?![A-Za-z0-9])` 后应能正确保护。"""
    text = "这是测试20 ms结束了吗好"
    lines = segment_text_into_lines(text, template=_zh_tpl(max_chars_per_line=6))
    # "20 ms" 应完整出现在某一行，绝不能被切成 "20" + "ms"
    assert any("20 ms" in line for line in lines), lines
    assert not any(line.strip().endswith("20") for line in lines), lines


def test_segment_protects_must_keep_term() -> None:
    """must_keep_terms 中的术语不该被切开。"""
    text = "介绍 Qwen 是端侧模型"
    # 若 Qwen 落在切点两侧就会被拆——设 max=6，'Qwen' 4 字符可能触边界
    lines = segment_text_into_lines(
        text, template=_zh_tpl(max_chars_per_line=6), must_keep_terms=["Qwen"]
    )
    assert any("Qwen" in line for line in lines)


def test_segment_empty_text() -> None:
    assert segment_text_into_lines("", template=_zh_tpl()) == []
    assert segment_text_into_lines("   ", template=_zh_tpl()) == []


# —— pack_lines_into_cue ——


def test_pack_single_line() -> None:
    cue = pack_lines_into_cue(
        "短句",
        start_ms=0,
        end_ms=1000,
        language="zh-CN",
        cue_id="c-0",
        template=_zh_tpl(),
    )
    assert len(cue.lines) == 1
    assert cue.lines[0].start_ms == 0 and cue.lines[0].end_ms == 1000


def test_pack_multiple_lines_share_duration() -> None:
    cue = pack_lines_into_cue(
        "这是一段较长的中文字幕内容",
        start_ms=1000,
        end_ms=5000,
        language="zh-CN",
        cue_id="c-0",
        template=_zh_tpl(max_chars_per_line=6, max_lines_per_cue=2),
    )
    assert len(cue.lines) == 2
    # 时间单调递增，覆盖整段
    assert cue.lines[0].start_ms == 1000
    assert cue.lines[-1].end_ms == 5000
    assert cue.lines[0].end_ms == cue.lines[1].start_ms


def test_pack_over_max_lines_merges_tail() -> None:
    """超过 max_lines_per_cue 时尾部合并到最后一行（不破口）。"""
    cue = pack_lines_into_cue(
        "abcdefghij" * 6,  # 60 chars，max_chars_per_line=10 → 6 行
        start_ms=0,
        end_ms=3000,
        language="en-US",
        cue_id="c-0",
        template=_en_tpl(max_chars_per_line=10, max_lines_per_cue=2),
    )
    assert len(cue.lines) <= 2


# —— 校验护栏 ——


def _clean_cue(cue_id: str, start: int, end: int, text: str = "短句") -> SubtitleCue:
    return SubtitleCue(
        id=cue_id,
        start_ms=start,
        end_ms=end,
        lines=[SubtitleLine(text=text, start_ms=start, end_ms=end, language="zh-CN")],
    )


def _clean_track(cues: list[SubtitleCue]) -> SubtitleTrack:
    return SubtitleTrack(
        id="tr",
        language="zh-CN",
        template_id="tpl",
        cues=cues,
        created_at=_T0,
    )


def test_validate_empty_track() -> None:
    tr = _clean_track([])
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_zh_tpl())]
    assert SubtitleIssueKind.EMPTY_TRACK in kinds


def test_validate_cue_too_short() -> None:
    tr = _clean_track([_clean_cue("c0", 0, 100)])  # 100ms < 500ms min
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_zh_tpl())]
    assert SubtitleIssueKind.CUE_TOO_SHORT in kinds


def test_validate_cue_too_long() -> None:
    tr = _clean_track([_clean_cue("c0", 0, 10000)])  # 10s > 6s max
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_zh_tpl())]
    assert SubtitleIssueKind.CUE_TOO_LONG in kinds


def test_validate_cue_overlap() -> None:
    tr = _clean_track(
        [
            _clean_cue("c0", 0, 2000),
            _clean_cue("c1", 1500, 3000),  # overlap
        ]
    )
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_zh_tpl())]
    assert SubtitleIssueKind.CUE_OVERLAP in kinds


def test_validate_cue_order_broken() -> None:
    tr = _clean_track(
        [
            _clean_cue("c0", 5000, 6000),
            _clean_cue("c1", 1000, 2000),  # 早于 c0
        ]
    )
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_zh_tpl())]
    assert SubtitleIssueKind.CUE_ORDER_BROKEN in kinds


def test_validate_reading_speed_zh() -> None:
    # cjk 上限 8 字/秒；14 字仅 1 秒 → 违规
    tr = _clean_track([_clean_cue("c0", 0, 1000, text="这里放十四个汉字来触发违规检测")])
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_zh_tpl())]
    assert SubtitleIssueKind.READING_SPEED_EXCEEDED in kinds


def test_validate_reading_speed_zh_ok() -> None:
    tr = _clean_track([_clean_cue("c0", 0, 2000, text="八个汉字一句刚好")])
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_zh_tpl())]
    assert SubtitleIssueKind.READING_SPEED_EXCEEDED not in kinds


def test_validate_reading_speed_en_row_with_cjk_char_still_uses_en_rules() -> None:
    """verifier REFUTED：首版 `_is_cjk(text)` 使 en 行含一个 CJK 字即整行走 CJK 规则；
    若模板未配 cjk_chars_per_sec 会跳过所有速度检查——护栏假阴性。
    修：按 line.language 决定规则，不看内容。"""
    tr = SubtitleTrack(
        id="tr",
        language="en-US",
        template_id="tpl-en",
        cues=[
            SubtitleCue(
                id="c0",
                start_ms=0,
                end_ms=500,
                lines=[
                    # 含一个 CJK 字符的 en 行；en_chars_per_sec 应仍然约束
                    SubtitleLine(
                        text="the very quick brown fox 世 jumps over lazy dog",
                        start_ms=0,
                        end_ms=500,
                        language="en-US",
                    ),
                ],
            )
        ],
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_en_tpl())]
    # 依然应命中英文 CPS 超速
    assert SubtitleIssueKind.READING_SPEED_EXCEEDED in kinds


def test_validate_reading_speed_en() -> None:
    tr = SubtitleTrack(
        id="tr",
        language="en-US",
        template_id="tpl-en",
        cues=[
            SubtitleCue(
                id="c0",
                start_ms=0,
                end_ms=500,
                lines=[
                    SubtitleLine(
                        text="the very quick brown fox jumps over lazy dog rapidly",
                        start_ms=0,
                        end_ms=500,
                        language="en-US",
                    ),
                ],
            )
        ],
        created_at=_T0,
    )
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_en_tpl())]
    assert SubtitleIssueKind.READING_SPEED_EXCEEDED in kinds


def test_validate_line_too_long() -> None:
    tr = _clean_track(
        [
            SubtitleCue(
                id="c0",
                start_ms=0,
                end_ms=2000,
                lines=[SubtitleLine(text="一" * 20, start_ms=0, end_ms=2000, language="zh-CN")],
            )
        ]
    )
    kinds = [
        i.kind
        for i in validate_subtitle_track(
            tr,
            template=_zh_tpl(max_chars_per_line=16),
        )
    ]
    assert SubtitleIssueKind.LINE_TOO_LONG in kinds


def test_validate_too_many_lines() -> None:
    tr = _clean_track(
        [
            SubtitleCue(
                id="c0",
                start_ms=0,
                end_ms=2000,
                lines=[
                    SubtitleLine(text=f"L{i}", start_ms=0, end_ms=2000, language="zh-CN")
                    for i in range(3)
                ],
            )
        ]
    )
    kinds = [
        i.kind
        for i in validate_subtitle_track(
            tr,
            template=_zh_tpl(max_lines_per_cue=2),
        )
    ]
    assert SubtitleIssueKind.TOO_MANY_LINES in kinds


def test_validate_word_out_of_line_span() -> None:
    tr = _clean_track(
        [
            SubtitleCue(
                id="c0",
                start_ms=0,
                end_ms=2000,
                lines=[
                    SubtitleLine(
                        text="hello",
                        start_ms=100,
                        end_ms=1000,
                        language="zh-CN",
                        words=[SubtitleWord(text="hello", start_ms=1500, end_ms=1900)],
                    )
                ],
            )
        ]
    )
    kinds = [i.kind for i in validate_subtitle_track(tr, template=_zh_tpl())]
    assert SubtitleIssueKind.WORD_TIME_OUT_OF_LINE in kinds


def test_is_valid_subtitle_track_true_on_clean() -> None:
    tr = _clean_track(
        [
            _clean_cue("c0", 0, 2000, text="八个字幕字数一"),
            _clean_cue("c1", 2500, 4500, text="八个字幕字数二"),
        ]
    )
    assert is_valid_subtitle_track(tr, template=_zh_tpl())


# —— 输出格式 ——


def test_render_srt_format() -> None:
    tr = _clean_track(
        [_clean_cue("c0", 0, 2000, text="第一句"), _clean_cue("c1", 3000, 5000, text="第二句")]
    )
    out = render_srt(tr)
    assert "1\n00:00:00,000 --> 00:00:02,000\n第一句" in out
    assert "2\n00:00:03,000 --> 00:00:05,000\n第二句" in out


def test_render_srt_multiline_uses_newline() -> None:
    cue = SubtitleCue(
        id="c0",
        start_ms=0,
        end_ms=2000,
        lines=[
            SubtitleLine(text="行1", start_ms=0, end_ms=1000, language="zh-CN"),
            SubtitleLine(text="行2", start_ms=1000, end_ms=2000, language="zh-CN"),
        ],
    )
    out = render_srt(_clean_track([cue]))
    assert "行1\n行2" in out


def test_render_ass_has_header_and_dialogue() -> None:
    tr = _clean_track([_clean_cue("c0", 0, 2000, text="测试")])
    out = render_ass(tr, template=_zh_tpl())
    assert "[Script Info]" in out
    assert "[V4+ Styles]" in out
    assert "[Events]" in out
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Default,测试" in out


def test_render_ass_multiline_uses_ass_newline() -> None:
    cue = SubtitleCue(
        id="c0",
        start_ms=0,
        end_ms=2000,
        lines=[
            SubtitleLine(text="L1", start_ms=0, end_ms=1000, language="zh-CN"),
            SubtitleLine(text="L2", start_ms=1000, end_ms=2000, language="zh-CN"),
        ],
    )
    out = render_ass(_clean_track([cue]), template=_zh_tpl())
    assert "L1\\NL2" in out


def test_to_timeline_overlay_shape() -> None:
    tr = _clean_track([_clean_cue("c0", 0, 2000, text="第一句")])
    overlay = to_timeline_overlay(tr)
    assert len(overlay) == 1
    assert overlay[0]["id"] == "c0"
    assert overlay[0]["start_ms"] == 0 and overlay[0]["end_ms"] == 2000
    assert overlay[0]["text"] == "第一句"
    assert overlay[0]["language"] == "zh-CN"


def test_render_dispatcher() -> None:
    tr = _clean_track([_clean_cue("c0", 0, 2000, text="x")])
    assert isinstance(render(tr, template=_zh_tpl(), format=SubtitleFormat.SRT), str)
    assert isinstance(render(tr, template=_zh_tpl(), format=SubtitleFormat.ASS), str)
    overlay = render(tr, template=_zh_tpl(), format=SubtitleFormat.TIMELINE_OVERLAY)
    assert isinstance(overlay, list) and len(overlay) == 1


def test_render_ass_color_hex_to_bgr() -> None:
    """ASS 颜色是 BGR：#FF0000 (红) 应转 &H000000FF..."""
    style = SubtitleStyleHint(color="#FF0000", outline_color="#00FF00")
    tpl = _zh_tpl(style_hint=style)
    tr = _clean_track([_clean_cue("c0", 0, 2000, text="x")])
    out = render_ass(tr, template=tpl)
    # #FF0000 → BGR 0000FF; #00FF00 → BGR 00FF00
    assert "0000FF" in out and "00FF00" in out


# —— SafeAreaSpec 边界 ——


def test_safe_area_bounds_ok() -> None:
    spec = SafeAreaSpec(left_min_pct=5, right_max_pct=95, top_min_pct=5, bottom_max_pct=90)
    assert spec.left_min_pct == 5


def test_safe_area_invalid_raises() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SafeAreaSpec(left_min_pct=50, right_max_pct=50)
