"""字幕合同（docs/modules/43 §5）。

- SubtitleTemplate：分段/阅读速度/安全区/最大行数/字体样式提示的**模板参数**（数据，非代码）；
  中文按字符/秒（CJK-CPS），英文按 CPS/WPM 分别配置——docs 明确要求"分开配置"。
- SubtitleLine：一行字幕（含 language、可选 karaoke words 与词级时间）。
- SubtitleCue：多行为一条 cue（同屏显示的整段），带 start/end/lines/style_ref/safe_area_hint。
- SubtitleTrack：一整轨字幕（多个 cue，同一 language + 模板）+ 源引用
  （Transcript 段 / LocalizedSentence）。
- SubtitleFormat：SRT / ASS / TIMELINE_OVERLAY 三种输出形式。

安全区（§5.3）：占位描述在 template.safe_area 里，实际每帧 occupied_regions 求解交给渲染层
（VF-306 CreativeTimeline V4 或未来的字幕布局求解器）；此处只承载 hint 与硬性上限（如
bottom_max_pct=95）供 QA（VF-309 CAPTION_OFF_SAFE_AREA 已实现）复核。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel


class SubtitleFormat(StrEnum):
    """字幕输出格式（渲染层 domain.render_* 消费）。"""

    SRT = "SRT"
    ASS = "ASS"
    TIMELINE_OVERLAY = "TIMELINE_OVERLAY"  # 进 CreativeTimeline V4_CAPTIONS 轨


class SafeAreaSpec(ContractModel):
    """安全区约束（归一化百分比 0-100）；渲染/QA 消费。默认覆盖抖音/TikTok 底部 UI 占位。"""

    left_min_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    right_max_pct: float = Field(default=95.0, ge=0.0, le=100.0)
    top_min_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    bottom_max_pct: float = Field(default=90.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _check_bounds(self) -> "SafeAreaSpec":
        if self.left_min_pct >= self.right_max_pct:
            raise ValueError("left_min_pct 必须 < right_max_pct")
        if self.top_min_pct >= self.bottom_max_pct:
            raise ValueError("top_min_pct 必须 < bottom_max_pct")
        return self


class SubtitleStyleHint(ContractModel):
    """字体样式提示（渲染层参考，不做真实 layout）。"""

    font_family: str | None = None
    font_size_pt: int | None = Field(default=None, gt=0)
    bold: bool = False
    color: str | None = Field(default=None, description="#RRGGBB")
    outline_color: str | None = Field(default=None, description="#RRGGBB")
    outline_width: float | None = Field(default=None, ge=0.0)


class SubtitleTemplate(ContractModel):
    """字幕模板：分段 + 阅读速度 + 安全区 + 样式（每语言/平台/账号一份，可版本化）。

    - max_chars_per_line：单行字符上限。中文按字符（含全角），英文按字符（近似 42）。
      两语言不同，故建议按 language 建两份模板；此字段配当前 language。
    - max_lines_per_cue：≤2（§5.1）；短视频默认 1。
    - cjk_chars_per_sec / en_chars_per_sec / en_words_per_sec：阅读速度上限（软阈值，超即 QA）。
    - min_cue_duration_ms：单条 cue 最短持续（避免闪现），默认 800ms。
    - max_cue_duration_ms：单条最长（避免长时间悬挂），默认 6000ms。
    - safe_area：安全区约束（渲染 + QA 消费）。
    - style_hint：字体/描边等提示（不承载真实字体渲染）。
    """

    id: str = Field(min_length=1)
    language: str = Field(min_length=1, description="模板绑定的字幕语言，如 zh-CN / en-US")
    max_chars_per_line: int = Field(gt=0)
    max_lines_per_cue: int = Field(default=2, ge=1, le=2)
    cjk_chars_per_sec: float | None = Field(default=None, gt=0.0,
                                                description="中文阅读速度上限，字/秒")
    en_chars_per_sec: float | None = Field(default=None, gt=0.0,
                                              description="英文 CPS 上限")
    en_words_per_sec: float | None = Field(default=None, gt=0.0,
                                              description="英文 WPM/60 上限，可选")
    min_cue_duration_ms: int = Field(default=800, ge=0)
    max_cue_duration_ms: int = Field(default=6000, ge=0)
    safe_area: SafeAreaSpec = Field(default_factory=SafeAreaSpec)
    style_hint: SubtitleStyleHint = Field(default_factory=SubtitleStyleHint)
    version: int = Field(default=1, ge=1)
    created_at: datetime

    @model_validator(mode="after")
    def _check_reading_speed_configured(self) -> "SubtitleTemplate":
        # 至少配一个语言的阅读速度上限，否则模板毫无意义
        if (self.cjk_chars_per_sec is None
                and self.en_chars_per_sec is None
                and self.en_words_per_sec is None):
            raise ValueError(
                "SubtitleTemplate 必须至少配一个阅读速度：cjk_chars_per_sec / "
                "en_chars_per_sec / en_words_per_sec"
            )
        if self.min_cue_duration_ms > self.max_cue_duration_ms:
            raise ValueError(
                f"min_cue_duration_ms({self.min_cue_duration_ms}) 必须 ≤ "
                f"max_cue_duration_ms({self.max_cue_duration_ms})"
            )
        return self


class SubtitleWord(ContractModel):
    """一行内的词级时间（karaoke / 逐词高亮）。仅在词级置信度达标时启用（§5.2）。"""

    text: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_span(self) -> "SubtitleWord":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        return self


class SubtitleLine(ContractModel):
    """一行字幕（cue 内多行的一条）。text 长度不宜超模板 max_chars_per_line（domain 校验）。"""

    text: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    language: str = Field(min_length=1)
    words: list[SubtitleWord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_span(self) -> "SubtitleLine":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        return self


class SubtitleCue(ContractModel):
    """一条 cue（同屏同时显示的整块字幕）。lines 数量应 ≤ template.max_lines_per_cue。"""

    id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    lines: list[SubtitleLine] = Field(min_length=1)
    source_ref_kind: str | None = Field(
        default=None, description="源引用类型：transcript_segment / localized_sentence",
    )
    source_ref_id: str | None = None
    safe_area_hint: SafeAreaSpec | None = Field(
        default=None,
        description="按帧 occupied_regions 求解的安全区（若渲染层已算好可填）",
    )
    style_ref: str | None = Field(default=None, description="引用 template.style_hint 或自定义")

    @model_validator(mode="after")
    def _check_span_and_lines(self) -> "SubtitleCue":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        for line in self.lines:
            if line.language and line.language.strip() == "":
                raise ValueError("line.language 不能为空")
        return self


class SubtitleTrack(ContractModel):
    """一整轨字幕（同语言 + 同模板）。cues 应按 start_ms 严格排序、不重叠——由 domain 校验。"""

    id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    cues: list[SubtitleCue] = Field(default_factory=list)
    source_transcript_id: str | None = None
    source_localization_variant_id: str | None = None
    alignment_provider: str | None = Field(
        default=None, description="产生词级时间的 provider 名（ASR / TTS forced align）",
    )
    created_at: datetime
