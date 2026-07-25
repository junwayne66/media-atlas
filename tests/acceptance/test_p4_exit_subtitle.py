"""P4 Exit 验收 —— 字幕 100% 通过安全区与阅读速度（docs/modules/43 §13 第 2 条）。

每句译文经 VF-402 分行/合成 cue，validate_subtitle_track 零违规（行长/CPS/重叠/时长）。
安全区由模板 SafeAreaSpec 结构性保证。非空跑护栏：超速 cue 必被 READING_SPEED_EXCEEDED 抓。
"""

from __future__ import annotations

from datetime import UTC, datetime

from p4_samples import SAMPLES

from videoforge_contracts import SafeAreaSpec, SubtitleTemplate, SubtitleTrack
from videoforge_domain import (
    SubtitleIssueKind,
    pack_lines_into_cue,
    validate_subtitle_track,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)
_SAFE = SafeAreaSpec()  # 默认覆盖抖音/TikTok 底部 UI（5/95/5/90 pct）


def _tpl(lang: str) -> SubtitleTemplate:
    if lang.startswith("zh"):
        return SubtitleTemplate(
            id="t-zh",
            language="zh-CN",
            max_chars_per_line=16,
            max_lines_per_cue=2,
            cjk_chars_per_sec=8.0,
            min_cue_duration_ms=500,
            max_cue_duration_ms=6000,
            safe_area=_SAFE,
            created_at=_T0,
        )
    return SubtitleTemplate(
        id="t-en",
        language="en-US",
        max_chars_per_line=42,
        max_lines_per_cue=2,
        en_chars_per_sec=17.0,
        en_words_per_sec=3.5,
        min_cue_duration_ms=500,
        max_cue_duration_ms=6000,
        safe_area=_SAFE,
        created_at=_T0,
    )


def _cue_for(s):
    tpl = _tpl(s.target_lang)
    return pack_lines_into_cue(
        s.target,
        start_ms=0,
        end_ms=s.duration_ms,
        language=s.target_lang,
        cue_id=s.sentence_id,
        template=tpl,
    ), tpl


def test_all_subtitles_pass_reading_speed_and_layout():
    violations = []
    for smp in SAMPLES:
        for s in smp.sentences:
            cue, tpl = _cue_for(s)
            track = SubtitleTrack(
                id=f"tr-{s.sentence_id}",
                language=s.target_lang,
                template_id=tpl.id,
                cues=[cue],
                created_at=_T0,
            )
            for issue in validate_subtitle_track(track, template=tpl):
                violations.append((s.sentence_id, issue.kind.value))
    assert violations == [], f"字幕应 100% 通过，违规：{violations}"


def test_reading_speed_check_is_not_vacuous():
    # 把一条 cue 压到极短时长 → CPS 爆表 → 必被抓（证明检查真的在跑）
    s = SAMPLES[0].sentences[0]
    tpl = _tpl(s.target_lang)
    fast_cue = pack_lines_into_cue(
        s.target,
        start_ms=0,
        end_ms=600,
        language=s.target_lang,
        cue_id=s.sentence_id,
        template=tpl,
    )
    track = SubtitleTrack(
        id="tr",
        language=s.target_lang,
        template_id=tpl.id,
        cues=[fast_cue],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_subtitle_track(track, template=tpl)}
    assert SubtitleIssueKind.READING_SPEED_EXCEEDED in kinds
