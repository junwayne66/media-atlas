"""文本轨合同（docs/modules/41 §8 OCR 与文字跟踪）。

OCR Provider 逐帧产出 TextObservation（检测框 + 识别文本 + 置信度）；跟踪把同一文本区域
跨帧聚成 TextTrack（IoU + 外观 + 光流），多帧投票定文本，并分类为字幕/标题/UI/水印等。
下游（Blueprint、审核 UI）只消费本合同，不依赖任何 OCR 引擎内部。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import TextTrackKind


class BBox(ContractModel):
    """归一化边界框（原点左上，x 向右、y 向下）。四边形退化为轴对齐框（MVP）。"""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _in_frame(self) -> "BBox":
        if self.x + self.w > 1.0001 or self.y + self.h > 1.0001:
            raise ValueError("bbox 超出画面（x+w 或 y+h > 1）")
        return self


class TextObservation(ContractModel):
    """单帧文本检测（OCR 原始输出，也是 TextTrack 的轨迹点）。"""

    frame_time_ms: int = Field(ge=0)
    bbox: BBox
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    occluded: bool = False


class TextTrack(ContractModel):
    """跨帧聚合的稳定文本轨（41 §8.6：时间范围、bbox、遮挡、运动、置信度、样式提示）。"""

    id: str = Field(min_length=1)
    source_artifact_id: str | None = None
    kind: TextTrackKind = TextTrackKind.UNKNOWN
    text: str = Field(description="多帧投票后的规范文本")
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    observations: list[TextObservation] = Field(default_factory=list, description="逐帧轨迹")
    motion: str | None = Field(default=None, description="STATIC / MOVING")
    style_hint: str | None = None
    low_confidence: bool = False

    @model_validator(mode="after")
    def _check_span(self) -> "TextTrack":
        if self.end_ms < self.start_ms:
            raise ValueError(f"end_ms({self.end_ms}) 必须 ≥ start_ms({self.start_ms})")
        return self


class TextTrackSet(ContractModel):
    """一次 OCR 分析产出的全部文本轨（顶层可持久化/交换合同）。"""

    id: str = Field(min_length=1)
    source_artifact_id: str | None = None
    tracks: list[TextTrack] = Field(default_factory=list)
    ocr_provider: str = Field(min_length=1)
    ocr_version: str | None = None
    created_at: datetime
