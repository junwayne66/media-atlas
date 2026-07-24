"""本地化审核合同（docs/modules/43 §12 语言 QA + §13 句级批准/局部重跑）。

VF-407 目标：把 VF-401..VF-406 各层的检查**聚合成逐句** QA 报告 + 句级审核状态 +
**局部重跑范围**。

- `LocalizationQAReport`：逐句 QA 发现（§12 自动检查），带发布门 `pass_or_block`。
- `LocalizationReview`：句级批准状态（原文/直译/适配稿并排后，人可只批准某句）。
- `ReRunScope`：改单句译文 → **只重跑该句 TTS/字幕/口型 + 下游渲染**（§13 验收），
  其它句命中缓存不动。

**红线（§12 + §13）**：`pass_or_block=True` 不能与任何 BLOCKER 发现共存（合同层硬拦，
手工构造的报告不能骗过发布门）；改单句的重跑范围**绝不**波及其它句的上游。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import QASeverity


class LocalizationQACheck(StrEnum):
    """§12 语言 QA 自动检查项。"""

    # 源/目标 Claim/数字/专名/否定一致
    CLAIM_CONSISTENCY = "CLAIM_CONSISTENCY"
    NUMBER_CONSISTENCY = "NUMBER_CONSISTENCY"
    PROPER_NOUN_CONSISTENCY = "PROPER_NOUN_CONSISTENCY"
    NEGATION_CONSISTENCY = "NEGATION_CONSISTENCY"
    # 术语表和读音
    GLOSSARY = "GLOSSARY"
    PRONUNCIATION = "PRONUNCIATION"
    # 未翻译 TextTrack
    UNTRANSLATED_TEXT = "UNTRANSLATED_TEXT"
    # 字幕行长/CPS/重叠/安全区
    SUBTITLE_LINE_LENGTH = "SUBTITLE_LINE_LENGTH"
    SUBTITLE_READING_SPEED = "SUBTITLE_READING_SPEED"
    SUBTITLE_OVERLAP = "SUBTITLE_OVERLAP"
    SUBTITLE_SAFE_AREA = "SUBTITLE_SAFE_AREA"
    # TTS 空白/重复/截断/音量/爆音
    TTS_GAP = "TTS_GAP"
    TTS_REPEAT = "TTS_REPEAT"
    TTS_TRUNCATION = "TTS_TRUNCATION"
    TTS_LEVEL = "TTS_LEVEL"
    TTS_CLIP = "TTS_CLIP"
    # 句级时长超限/极端变速
    DURATION_EXCEEDED = "DURATION_EXCEEDED"
    EXTREME_SPEED = "EXTREME_SPEED"
    # 人脸段口型/音频粗同步
    LIPSYNC_SYNC = "LIPSYNC_SYNC"
    AV_SYNC = "AV_SYNC"


class ReviewState(StrEnum):
    """句级审核状态（§12 人工界面：批准可针对句子）。"""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EDITED = "EDITED"  # 人工改了译文（须携 edited_text，触发局部重跑）


class ReRunStage(StrEnum):
    """本地化流水线阶段（§13 局部重跑范围）。"""

    TRANSLATION = "TRANSLATION"
    TTS = "TTS"
    SUBTITLE = "SUBTITLE"
    LIPSYNC = "LIPSYNC"
    AUDIO_MIX = "AUDIO_MIX"
    RENDER = "RENDER"


class LocalizationQAFinding(ContractModel):
    """一条逐句 QA 发现。"""

    sentence_id: str = Field(min_length=1)
    check: LocalizationQACheck
    severity: QASeverity
    detail: str = Field(min_length=1)
    evidence: dict[str, object] = Field(default_factory=dict)


class LocalizationQAReport(ContractModel):
    """一个 LocalizationVariant 的语言 QA 报告。

    `pass_or_block` 必须由 domain 的发布门计算；合同层交叉校验拒绝
    `pass_or_block=True` 与任何 BLOCKER 并存——手工构造的报告骗不过门。
    """

    id: str = Field(min_length=1)
    localization_variant_id: str = Field(min_length=1)
    findings: list[LocalizationQAFinding] = Field(default_factory=list)
    reviewed_sentence_ids: list[str] = Field(default_factory=list)
    pass_or_block: bool
    created_at: datetime

    @model_validator(mode="after")
    def _check_gate_integrity(self) -> "LocalizationQAReport":
        if self.pass_or_block and any(
            f.severity is QASeverity.BLOCKER for f in self.findings
        ):
            raise ValueError(
                "pass_or_block=True 不能与 BLOCKER 发现并存"
                "（必须调用 domain.validate_localization_publish_gate 计算）"
            )
        return self


class SentenceReviewDecision(ContractModel):
    """对单句的审核决策。EDITED 必须携带 edited_text。"""

    sentence_id: str = Field(min_length=1)
    state: ReviewState
    reviewer: str | None = None
    note: str | None = None
    edited_text: str | None = Field(
        default=None, description="EDITED 时的新译文；其它状态必须为 None",
    )

    @model_validator(mode="after")
    def _check_edit(self) -> "SentenceReviewDecision":
        if self.state is ReviewState.EDITED and not self.edited_text:
            raise ValueError("EDITED 状态必须携带非空 edited_text")
        if self.state is not ReviewState.EDITED and self.edited_text is not None:
            raise ValueError("只有 EDITED 状态可携带 edited_text")
        return self


class LocalizationReview(ContractModel):
    """一个 LocalizationVariant 的句级审核集合。"""

    id: str = Field(min_length=1)
    localization_variant_id: str = Field(min_length=1)
    decisions: list[SentenceReviewDecision] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def _check_unique(self) -> "LocalizationReview":
        seen: set[str] = set()
        for d in self.decisions:
            if d.sentence_id in seen:
                raise ValueError(f"同一 sentence_id 出现两次：{d.sentence_id!r}")
            seen.add(d.sentence_id)
        return self
