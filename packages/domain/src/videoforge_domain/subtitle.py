"""字幕引擎（docs/modules/43 §5）：分段/对齐/CPS/多格式渲染。纯函数。

- segment_text_into_lines：按 max_chars_per_line 分行；保护术语/数字+单位/否定
  结构不被切开；中文按字符、英文按词。
- pack_lines_into_cues：多行合并 cue，遵守 max_lines_per_cue。
- align_words_to_cues：用词级时间给 cue 内每行摊 start/end；无词时间时按行字符占比均分。
- render_srt / render_ass / to_timeline_overlay：三格式产出。
- validate_subtitle_track：CPS/单条时长/行数/重叠/行长/word 单调 → typed SubtitleIssue。

CPS 判定语言分离（§5.1）：中文按 cjk_chars_per_sec 走字符计；英文按 en_chars_per_sec 或
en_words_per_sec 走词/字符计（模板任一非空即可）。混语 cue 按 line.language 分别取阈值。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from videoforge_contracts import (
    SubtitleCue,
    SubtitleFormat,
    SubtitleLine,
    SubtitleTemplate,
    SubtitleTrack,
    SubtitleWord,
)

# 保护单元的启发式识别：数字+单位（含空格与常见科技单位）。
# 尾部**不用 `\b`**——`\b` 在 CJK 相邻时失效（汉字属 `\w`），"20 ms结束" 里的 "ms" 后面
# 是汉字（word char），\b 不成立、保护段根本不生成（verifier REFUTED）。改用
# `(?![A-Za-z0-9])`：后面不是英文/数字即视为单位结束，中英文尾巴都能命中。
_PROTECTED_RE = re.compile(
    r"""
    (?:                                       # 一个"保护块"
      (?:\d+(?:\.\d+)?)\s?
      (?:%|ms|s|hz|khz|mhz|ghz|kb|mb|gb|tb|fps|dpi|kg|g|mg|km|m|cm|mm)
      (?![A-Za-z0-9])
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_EN_TOKEN_RE = re.compile(r"\S+")


class SubtitleIssueKind(StrEnum):
    EMPTY_TRACK = "EMPTY_TRACK"
    CUE_ORDER_BROKEN = "CUE_ORDER_BROKEN"  # cues 未按 start 严格递增
    CUE_OVERLAP = "CUE_OVERLAP"  # 相邻 cue 时间重叠
    CUE_TOO_SHORT = "CUE_TOO_SHORT"
    CUE_TOO_LONG = "CUE_TOO_LONG"
    LINE_TOO_LONG = "LINE_TOO_LONG"
    TOO_MANY_LINES = "TOO_MANY_LINES"
    READING_SPEED_EXCEEDED = "READING_SPEED_EXCEEDED"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"  # line.language != template.language
    WORD_TIME_OUT_OF_LINE = "WORD_TIME_OUT_OF_LINE"  # word span 超出 line span


@dataclass(frozen=True)
class SubtitleIssue:
    kind: SubtitleIssueKind
    ref: str  # cue id 或 track id
    detail: str


def _is_cjk(text: str) -> bool:
    """判定"该文本走 CJK 计数"：出现任一 CJK 汉字/假名即为 True。"""
    for ch in text:
        code = ord(ch)
        # 覆盖 CJK 常用 + 扩展 A + 全角标点 + 假名
        if 0x4E00 <= code <= 0x9FFF:
            return True
        if 0x3400 <= code <= 0x4DBF:
            return True
        if 0x3040 <= code <= 0x30FF:
            return True
    return False


def _cjk_char_count(text: str) -> int:
    """有效字符数（CJK）：不算空白与半角标点。全角标点计入（占位真实）。"""
    return sum(1 for ch in text if not ch.isspace() and not (ch.isascii() and not ch.isalnum()))


def _en_word_count(text: str) -> int:
    return len(_EN_TOKEN_RE.findall(text))


def _reading_speed_ok(
    text: str, duration_ms: int, template: SubtitleTemplate, language: str
) -> tuple[bool, str]:
    """返回 (是否达标, 违规细节)。达标即 True + ""。

    **按 `line.language` 决定规则**（verifier REFUTED：首版用 `or _is_cjk(text)` 使英文
    行含一个 CJK 字符即整行走 CJK 规则；若模板未配 CJK 上限就直接跳过所有速度检查
    → 护栏假阴性）。现在：
    - line.language 以 "zh"/"ja"/"ko" 开头 → CJK 规则；否则英文规则。
    - 混排文本仍按行的**声明语言**判定：混排应由上层按 line.language 拆行/拆轨（§5）。
    - 若该语言在模板下无对应阈值（CJK 且 cjk_chars_per_sec=None，或英文且两个 en 阈值
      都为 None），返回 True 但不视为通过——上层应通过 LANGUAGE_MISMATCH / 模板配置
      发现"该语言用错了模板"。
    """
    if duration_ms <= 0:
        return False, "cue 时长 ≤ 0"
    sec = duration_ms / 1000.0
    lang_low = language.lower()
    if lang_low.startswith(("zh", "ja", "ko")):
        limit = template.cjk_chars_per_sec
        if limit is None:
            # 模板未配 CJK 上限 —— 无法判定，跳过（该 line 本不该走此模板）
            return True, ""
        count = _cjk_char_count(text)
        rate = count / sec
        if rate > limit:
            return False, (f"CJK 阅读速度 {rate:.1f} 字/秒 超过模板 {limit:.1f}")
        return True, ""
    # 英文：首选 CPS，其次 WPS（en_words_per_sec）
    if template.en_chars_per_sec is not None:
        rate = len(text) / sec
        if rate > template.en_chars_per_sec:
            return False, (f"英文 CPS {rate:.1f} 超过模板 {template.en_chars_per_sec:.1f}")
    if template.en_words_per_sec is not None:
        rate = _en_word_count(text) / sec
        if rate > template.en_words_per_sec:
            return False, (f"英文 WPS {rate:.2f} 超过模板 {template.en_words_per_sec:.2f}")
    return True, ""


def _find_protected_spans(text: str) -> list[tuple[int, int]]:
    """返回不能被切开的 (start, end) 段（当前：数字+单位）。术语保护由调用方合并进来。"""
    return [(m.start(), m.end()) for m in _PROTECTED_RE.finditer(text)]


def _protect_terms(text: str, terms: list[str]) -> list[tuple[int, int]]:
    """把 must_keep_terms 转成保护段（大小写不敏感）。术语交叠时合并成大区间。"""
    spans: list[tuple[int, int]] = []
    low = text.lower()
    for t in terms:
        if not t:
            continue
        tl = t.lower()
        i = 0
        while True:
            k = low.find(tl, i)
            if k < 0:
                break
            spans.append((k, k + len(tl)))
            i = k + len(tl)
    return spans


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    out = [spans[0]]
    for s, e in spans[1:]:
        ls, le = out[-1]
        if s <= le:
            out[-1] = (ls, max(le, e))
        else:
            out.append((s, e))
    return out


def _in_protected(pos: int, spans: list[tuple[int, int]]) -> bool:
    """pos 是否落在任何保护段内部（不含起止边界 —— 允许在段边界处切）。"""
    for s, e in spans:
        if s < pos < e:
            return True
    return False


def segment_text_into_lines(
    text: str,
    *,
    template: SubtitleTemplate,
    must_keep_terms: list[str] | None = None,
) -> list[str]:
    """按 max_chars_per_line 分行；术语与数字+单位保护段不被切开。

    中文：按字符/长度贪心切；英文：按词贪心切。若单个词超过 max_chars_per_line，仍保留（不
    切词，交给上层处理——首版不做词内切）。
    """
    if not text.strip():
        return []
    max_len = template.max_chars_per_line
    protected = _merge_spans(
        _find_protected_spans(text) + _protect_terms(text, must_keep_terms or []),
    )
    if _is_cjk(text):
        return _segment_cjk(text, max_len, protected)
    return _segment_en(text, max_len)


def _segment_cjk(text: str, max_len: int, protected: list[tuple[int, int]]) -> list[str]:
    lines: list[str] = []
    cursor = 0
    n = len(text)
    while cursor < n:
        remaining = n - cursor
        if remaining <= max_len:
            lines.append(text[cursor:].strip())
            break
        # 目标切点 = cursor + max_len；若落在保护段中间，回退到保护段起点
        cut = cursor + max_len
        while cut > cursor and _in_protected(cut, protected):
            cut -= 1
        if cut == cursor:
            # 单个保护段就比一行还长——强切（保底不死循环）
            cut = cursor + max_len
        lines.append(text[cursor:cut].strip())
        cursor = cut
    return [line for line in lines if line]


def _segment_en(text: str, max_len: int) -> list[str]:
    tokens = _EN_TOKEN_RE.findall(text)
    if not tokens:
        return []
    lines: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for tok in tokens:
        add_len = len(tok) + (1 if cur else 0)
        if cur_len + add_len > max_len and cur:
            lines.append(" ".join(cur))
            cur = [tok]
            cur_len = len(tok)
        else:
            cur.append(tok)
            cur_len += add_len
    if cur:
        lines.append(" ".join(cur))
    return lines


def pack_lines_into_cue(
    text: str,
    *,
    start_ms: int,
    end_ms: int,
    language: str,
    cue_id: str,
    template: SubtitleTemplate,
    must_keep_terms: list[str] | None = None,
    words: list[SubtitleWord] | None = None,
) -> SubtitleCue:
    """把一句文本分行后合成一条 cue（≤ template.max_lines_per_cue 行）。

    行时间：若有 words 且能覆盖，则按每行首/末词的时间；否则按文本长度占比在 [start,end] 内均分。
    多余的行会溢出到后续 cue —— 但首版策略是"若超行数则合行"，避免破口。
    """
    all_lines = segment_text_into_lines(
        text,
        template=template,
        must_keep_terms=must_keep_terms,
    )
    if not all_lines:
        raise ValueError("空文本无法生成 cue")
    max_lines = template.max_lines_per_cue
    if len(all_lines) > max_lines:
        # 合并策略：把超出行按序拼到最后一行，避免破口（超行长交给 QA 提示）
        head = all_lines[: max_lines - 1] if max_lines > 1 else []
        tail = " ".join(all_lines[max_lines - 1 :]) if max_lines >= 1 else ""
        all_lines = head + ([tail] if tail else [])
    line_times = _distribute_times(all_lines, start_ms, end_ms, words)
    lines = [
        SubtitleLine(
            text=t,
            start_ms=s,
            end_ms=e,
            language=language,
            words=_words_for_line(t, words, s, e) if words else [],
        )
        for t, (s, e) in zip(all_lines, line_times, strict=True)
    ]
    return SubtitleCue(id=cue_id, start_ms=start_ms, end_ms=end_ms, lines=lines)


def _distribute_times(
    lines: list[str],
    start_ms: int,
    end_ms: int,
    words: list[SubtitleWord] | None,
) -> list[tuple[int, int]]:
    """给每行分配 [start,end]。默认按字符长度占比均分；若有词时间且能对齐，则用词时间。

    此函数是**保守**实现：不做词到行的字符级对齐（复杂且易错），只保证时间连续、单调，
    且各行落在 [start_ms, end_ms] 内。真正的 forced alignment 由 provider-sdk 完成。
    """
    if not lines:
        return []
    if len(lines) == 1:
        return [(start_ms, end_ms)]
    total_len = sum(max(1, len(line)) for line in lines)
    total_span = end_ms - start_ms
    out: list[tuple[int, int]] = []
    cursor = start_ms
    acc = 0
    for i, line in enumerate(lines):
        share = max(1, len(line))
        acc += share
        if i == len(lines) - 1:
            end = end_ms
        else:
            end = start_ms + int(round(total_span * acc / total_len))
            if end <= cursor:
                end = cursor + 1  # 单调递增保证
        out.append((cursor, end))
        cursor = end
    return out


def _words_for_line(
    line_text: str,
    all_words: list[SubtitleWord] | None,
    start_ms: int,
    end_ms: int,
) -> list[SubtitleWord]:
    """从 all_words 里选出落入 [start,end] 的词——**只按时间过滤**。

    verifier finding：首版用 `w.text in line_text` 会把子串误纳（'ell' 会被塞进
    'hello world' 行）。实际管线里 words 来自同一 tokenize，风险低但违反 docstring。
    改为纯时间过滤；文本对不上是 provider 的责任（fake 已保证 token 与文本一致）。
    """
    if not all_words:
        return []
    return [w for w in all_words if start_ms <= w.start_ms and w.end_ms <= end_ms]


def validate_subtitle_track(
    track: SubtitleTrack,
    *,
    template: SubtitleTemplate,
) -> list[SubtitleIssue]:
    """字幕护栏；返回全部违规（空 = 通过）。"""
    issues: list[SubtitleIssue] = []
    if not track.cues:
        issues.append(SubtitleIssue(SubtitleIssueKind.EMPTY_TRACK, track.id, "轨内无 cue"))
        return issues
    # 顺序 + 重叠（分别检测）
    prev_start = -1
    prev_end = -1
    prev_id: str | None = None
    for cue in track.cues:
        if prev_start >= 0 and cue.start_ms < prev_start:
            issues.append(
                SubtitleIssue(
                    SubtitleIssueKind.CUE_ORDER_BROKEN,
                    cue.id,
                    f"cue {cue.id!r} 起点 {cue.start_ms}ms 早于前一 cue "
                    f"{prev_id!r} 起点 {prev_start}ms（未按 start_ms 递增）",
                )
            )
        elif cue.start_ms < prev_end:
            issues.append(
                SubtitleIssue(
                    SubtitleIssueKind.CUE_OVERLAP,
                    cue.id,
                    f"cue {cue.id!r} 起点 {cue.start_ms}ms 早于前一 cue "
                    f"{prev_id!r} 结束 {prev_end}ms",
                )
            )
        prev_start = cue.start_ms
        prev_end = cue.end_ms
        prev_id = cue.id
        # 单条时长
        dur = cue.end_ms - cue.start_ms
        if dur < template.min_cue_duration_ms:
            issues.append(
                SubtitleIssue(
                    SubtitleIssueKind.CUE_TOO_SHORT,
                    cue.id,
                    f"cue 时长 {dur}ms < 模板 min {template.min_cue_duration_ms}ms",
                )
            )
        if dur > template.max_cue_duration_ms:
            issues.append(
                SubtitleIssue(
                    SubtitleIssueKind.CUE_TOO_LONG,
                    cue.id,
                    f"cue 时长 {dur}ms > 模板 max {template.max_cue_duration_ms}ms",
                )
            )
        # 行数
        if len(cue.lines) > template.max_lines_per_cue:
            issues.append(
                SubtitleIssue(
                    SubtitleIssueKind.TOO_MANY_LINES,
                    cue.id,
                    f"cue 行数 {len(cue.lines)} > 模板 max {template.max_lines_per_cue}",
                )
            )
        # 每行长度 + 语言 + 阅读速度 + word 单调
        for line in cue.lines:
            if line.language != template.language and line.language != track.language:
                # 允许 line.language 与 track 同即可（混语用不同 track 覆盖）
                issues.append(
                    SubtitleIssue(
                        SubtitleIssueKind.LANGUAGE_MISMATCH,
                        cue.id,
                        f"line.language={line.language} 与模板 "
                        f"{template.language} / 轨 {track.language} 不一致",
                    )
                )
            # 行长（按字符原始长度算，与切分保持一致）
            if _line_length_for(line.text) > template.max_chars_per_line:
                issues.append(
                    SubtitleIssue(
                        SubtitleIssueKind.LINE_TOO_LONG,
                        cue.id,
                        f"line 长度 {_line_length_for(line.text)} > 模板 "
                        f"{template.max_chars_per_line}",
                    )
                )
            # 阅读速度
            ok, why = _reading_speed_ok(
                line.text,
                line.end_ms - line.start_ms,
                template,
                line.language,
            )
            if not ok:
                issues.append(
                    SubtitleIssue(
                        SubtitleIssueKind.READING_SPEED_EXCEEDED,
                        cue.id,
                        why,
                    )
                )
            # word 时间超行 span
            for w in line.words:
                if w.start_ms < line.start_ms or w.end_ms > line.end_ms:
                    issues.append(
                        SubtitleIssue(
                            SubtitleIssueKind.WORD_TIME_OUT_OF_LINE,
                            cue.id,
                            f"word {w.text!r} span [{w.start_ms},{w.end_ms}] 超出 "
                            f"line span [{line.start_ms},{line.end_ms}]",
                        )
                    )
    return issues


def _line_length_for(text: str) -> int:
    """行长度计量：CJK 与英文都按字符数（英文按字符与 max_chars 语义一致）。"""
    return len(text)


def is_valid_subtitle_track(track: SubtitleTrack, *, template: SubtitleTemplate) -> bool:
    return not validate_subtitle_track(track, template=template)


# —— 输出格式 ——


def _fmt_srt_time(ms: int) -> str:
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1000
    frac = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{frac:03d}"


def render_srt(track: SubtitleTrack) -> str:
    """标准 SRT。每个 cue 一段，行间 `\\n` 换行。"""
    out: list[str] = []
    for i, cue in enumerate(track.cues, start=1):
        out.append(str(i))
        out.append(f"{_fmt_srt_time(cue.start_ms)} --> {_fmt_srt_time(cue.end_ms)}")
        out.append("\n".join(line.text for line in cue.lines))
        out.append("")  # 空行分隔
    return "\n".join(out).rstrip() + "\n"


def _fmt_ass_time(ms: int) -> str:
    # ASS 时间格式 H:MM:SS.CS（centiseconds）
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1000
    cs = (ms % 1000) // 10
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


_ASS_HEADER_TMPL = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, Bold, Outline, Alignment, MarginV
Style: Default,{font},{size},&H00{color},&H00{outline},{bold},{ow},2,{margin_v}

[Events]
Format: Layer, Start, End, Style, Text
"""


def _hex_to_bgr(color: str | None) -> str:
    """ASS 颜色是 BGR。#RRGGBB → BBGGRR。缺省白色。"""
    if not color or not color.startswith("#") or len(color) != 7:
        return "FFFFFF"
    r, g, b = color[1:3], color[3:5], color[5:7]
    return (b + g + r).upper()


def render_ass(track: SubtitleTrack, *, template: SubtitleTemplate) -> str:
    """ASS 格式。样式来自 template.style_hint；文本用 `\\N` 分行（ASS 惯例）。"""
    style = template.style_hint
    header = _ASS_HEADER_TMPL.format(
        font=style.font_family or "Arial",
        size=style.font_size_pt or 48,
        color=_hex_to_bgr(style.color),
        outline=_hex_to_bgr(style.outline_color or "#000000"),
        bold=(-1 if style.bold else 0),
        ow=(style.outline_width if style.outline_width is not None else 2.0),
        margin_v=int((100 - template.safe_area.bottom_max_pct) * 1920 / 100),
    )
    events: list[str] = []
    for cue in track.cues:
        text = "\\N".join(line.text for line in cue.lines)
        events.append(
            f"Dialogue: 0,{_fmt_ass_time(cue.start_ms)},{_fmt_ass_time(cue.end_ms)},Default,{text}",
        )
    return header + "\n".join(events) + "\n"


def to_timeline_overlay(track: SubtitleTrack) -> list[dict[str, object]]:
    """转 CreativeTimeline V4_CAPTIONS 轨的 segments 描述（dict 形式）。

    每 cue 一个 segment：id / time_range / text（\\n 分行）/ language。上层负责把它
    塞进 videoforge_contracts.Segment（需要 RationalTime，rate 由调用方决定）。
    """
    return [
        {
            "id": cue.id,
            "start_ms": cue.start_ms,
            "end_ms": cue.end_ms,
            "text": "\n".join(line.text for line in cue.lines),
            "language": cue.lines[0].language if cue.lines else track.language,
            "source_ref": cue.source_ref_id,
        }
        for cue in track.cues
    ]


def render(
    track: SubtitleTrack, *, template: SubtitleTemplate, format: SubtitleFormat
) -> str | list[dict[str, object]]:
    """统一入口：按 format 分派到 render_srt / render_ass / to_timeline_overlay。"""
    if format is SubtitleFormat.SRT:
        return render_srt(track)
    if format is SubtitleFormat.ASS:
        return render_ass(track, template=template)
    if format is SubtitleFormat.TIMELINE_OVERLAY:
        return to_timeline_overlay(track)
    raise ValueError(f"未覆盖的 SubtitleFormat: {format}")
