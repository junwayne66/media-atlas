"""OCR 端口 + Fake（docs/modules/41 §8）。

OCR Provider 逐帧产出 TextObservation（检测框 + 识别文本 + 置信度）——业务不依赖任何
OCR 引擎内部。真实引擎（PaddleOCR / 中英识别模型）需模型，属停止条件延后：默认
UnconfiguredOCRProvider 诚实返回 UNCONFIGURED，不静默假装；FakeOCRProvider 回放录制检测。

跟踪/多帧投票/类型分类是 domain 的纯后处理（track_text_observations），本层不做——
Provider 只吐原始逐帧检测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from videoforge_contracts import TextObservation


class OCRStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"  # 真实引擎未接入（需模型，停止条件）


class OCRErrorCode(StrEnum):
    OCR_LOW_COVERAGE = "OCR_LOW_COVERAGE"  # §12：覆盖率过低
    UNCONFIGURED = "UNCONFIGURED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class OCRRequest:
    video_path: Path
    languages: tuple[str, ...] = ("zh-CN", "en-US")
    # 采样帧时间（ms）：关键帧 + 场景切换附近（41 §8.1）；空则由 Provider 决定
    frame_times_ms: tuple[int, ...] = ()


@dataclass
class OCRResult:
    status: OCRStatus
    provider: str
    observations: list[TextObservation] = field(default_factory=list)
    error_code: OCRErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OCRStatus.OK


@runtime_checkable
class OCRProvider(Protocol):
    name: str
    languages: tuple[str, ...]
    execution_location: str

    def detect(self, request: OCRRequest) -> OCRResult: ...

    def health_check(self) -> OCRResult: ...


class UnconfiguredOCRProvider:
    """默认：真实引擎未接入（需模型）。返回 UNCONFIGURED，不静默假装。"""

    def __init__(
        self,
        name: str = "ocr.unconfigured",
        *,
        languages: tuple[str, ...] = ("zh-CN", "en-US"),
        execution_location: str = "local",
    ) -> None:
        self.name = name
        self.languages = languages
        self.execution_location = execution_location

    def detect(self, request: OCRRequest) -> OCRResult:
        return OCRResult(
            status=OCRStatus.UNCONFIGURED,
            provider=self.name,
            error_code=OCRErrorCode.UNCONFIGURED,
            detail="OCR 引擎未接入（需模型/授权）；请人工标注或稍后重试",
        )

    def health_check(self) -> OCRResult:
        return self.detect(OCRRequest(video_path=Path("/dev/null")))


class FakeOCRProvider:
    """回放录制逐帧检测（供下游跟踪/审核开发）。全程不触模型。"""

    def __init__(
        self,
        *,
        name: str,
        observations: list[TextObservation],
        languages: tuple[str, ...] = ("zh-CN", "en-US"),
        execution_location: str = "local",
    ) -> None:
        self.name = name
        # 深拷贝隔离：合同模型非 frozen（validate_assignment，可变），若只浅拷贝，外部改动
        # 入参/返回的元素会污染内部录制、殃及后续调用
        self._observations = [o.model_copy(deep=True) for o in observations]
        self.languages = languages
        self.execution_location = execution_location

    def detect(self, request: OCRRequest) -> OCRResult:
        return OCRResult(
            status=OCRStatus.OK,
            provider=self.name,
            observations=[o.model_copy(deep=True) for o in self._observations],
        )

    def health_check(self) -> OCRResult:
        return OCRResult(status=OCRStatus.OK, provider=self.name)
