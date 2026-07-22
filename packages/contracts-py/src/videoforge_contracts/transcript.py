"""统一词级转录合同（docs/modules/41 §7.2）。

ASR Provider（whisper.cpp / WhisperX / FunASR …）统一产出本合同：段级 + 词级时间、
语言、置信度、说话人。低置信词/段带审核标记。保存 ASR/VAD/对齐/说话人模型版本以可重放。
下游（Blueprint、审核 UI）只消费本合同，不依赖任何 ASR 引擎内部结构。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel


class TranscriptWord(ContractModel):
    """词级时间与置信度。低置信词进入审核标记（41 §7.2）。"""

    text: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    low_confidence: bool = False

    @model_validator(mode="after")
    def _check_span(self) -> "TranscriptWord":
        if self.end_ms < self.start_ms:
            raise ValueError(f"end_ms({self.end_ms}) 必须 ≥ start_ms({self.start_ms})")
        return self


class TranscriptSegment(ContractModel):
    """段级转录（一个说话片段）。混语时按段带各自 language（41 §7.1）。"""

    id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    speaker_id: str | None = Field(default=None, description="说话人聚类 id，如 spk_0")
    language: str = Field(min_length=1, description="BCP-47，如 zh-CN / en-US")
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    words: list[TranscriptWord] = Field(default_factory=list)
    low_confidence: bool = False

    @model_validator(mode="after")
    def _check_span(self) -> "TranscriptSegment":
        if self.end_ms < self.start_ms:
            raise ValueError(f"end_ms({self.end_ms}) 必须 ≥ start_ms({self.start_ms})")
        return self


class TranscriptModels(ContractModel):
    """可重放：ASR/VAD/对齐/说话人模型与版本（41 §7.2「保存 VAD、对齐和说话人模型版本」）。"""

    asr_provider: str = Field(min_length=1, description="如 asr.whisper_cpp / asr.whisperx")
    asr_model: str | None = Field(default=None, description="如 medium / large-v3")
    asr_version: str | None = None
    vad_version: str | None = None
    align_version: str | None = None
    speaker_version: str | None = None


class Transcript(ContractModel):
    """一次转录的统一产出（词级合同）。段内可含不同语言（混语）。"""

    id: str = Field(min_length=1)
    source_artifact_id: str | None = Field(default=None, description="源音频/视频 Artifact")
    language: str = Field(min_length=1, description="主语言；混语时各段带自身 language")
    segments: list[TranscriptSegment] = Field(default_factory=list)
    models: TranscriptModels
    hotwords: list[str] = Field(
        default_factory=list, description="注入的热词（产品名/人名），用于中文热点词偏置"
    )
    duration_ms: int | None = Field(default=None, ge=0)
    created_at: datetime
