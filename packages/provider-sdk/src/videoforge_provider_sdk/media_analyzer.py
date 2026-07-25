"""媒体分析 Provider 端口 + Fake（docs/modules/42 §11）。

分析渲染成品的**帧样本 / 音频窗 / 字幕包围盒 / 时长**，交由 domain 规则引擎判定 QAFinding。
真实检测器（ebur128 for loudness / opencv for luma+phash / OCR bbox）属停止条件延后：
默认 UnconfiguredMediaAnalyzerProvider 返回 UNCONFIGURED；Fake 回放测试注入的样本，不做 I/O。

分层：本端口 **contracts-only**（不 import domain），返回的样本是简单值对象，供 domain 消费。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class MediaAnalyzerStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"


class MediaAnalyzerErrorCode(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    MEDIA_UNREADABLE = "MEDIA_UNREADABLE"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class FrameSample:
    at_ms: int
    mean_luma: float
    phash: str


@dataclass(frozen=True)
class AudioWindow:
    at_ms: int
    duration_ms: int
    lufs: float
    true_peak_dbtp: float
    has_voice: bool
    tail_amplitude: float


@dataclass(frozen=True)
class CaptionBBox:
    caption_id: str
    at_ms: int
    duration_ms: int
    left_pct: float
    top_pct: float
    right_pct: float
    bottom_pct: float


@dataclass(frozen=True)
class MediaAnalysisRequest:
    """媒体分析请求：媒体路径（受调用方白名单约束）+ 采样参数。"""

    resolved_path: str
    fps: float = 30.0
    audio_window_ms: int = 5000


@dataclass
class MediaAnalysisResult:
    status: MediaAnalyzerStatus
    provider: str
    frame_samples: list[FrameSample] = field(default_factory=list)
    audio_windows: list[AudioWindow] = field(default_factory=list)
    captions: list[CaptionBBox] = field(default_factory=list)
    measured_duration_ms: int = 0
    broll_duration_ms: int = 0
    total_video_duration_ms: int = 0
    error_code: MediaAnalyzerErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == MediaAnalyzerStatus.OK


@runtime_checkable
class MediaAnalyzerProvider(Protocol):
    name: str
    execution_location: str

    def analyze(self, request: MediaAnalysisRequest) -> MediaAnalysisResult:
        """分析媒体成品，返回帧/音频/字幕/时长样本供 domain 规则引擎消费。"""
        ...

    def health_check(self) -> MediaAnalysisResult: ...


class UnconfiguredMediaAnalyzerProvider:
    """默认：真实检测器（ebur128/opencv/OCR）未接入。诚实 UNCONFIGURED，绝不静默假装。"""

    def __init__(
        self,
        *,
        name: str = "media_analyzer.unconfigured",
        execution_location: str = "local",
    ) -> None:
        self.name = name
        self.execution_location = execution_location

    def analyze(self, request: MediaAnalysisRequest) -> MediaAnalysisResult:
        return MediaAnalysisResult(
            status=MediaAnalyzerStatus.UNCONFIGURED,
            provider=self.name,
            error_code=MediaAnalyzerErrorCode.UNCONFIGURED,
            detail="媒体分析器未接入（缺 ebur128/opencv/OCR）；请人工审片或稍后重试",
        )

    def health_check(self) -> MediaAnalysisResult:
        return MediaAnalysisResult(status=MediaAnalyzerStatus.UNCONFIGURED, provider=self.name)


class FakeMediaAnalyzerProvider:
    """确定性 Fake：回放构造时注入的样本，不做 I/O、不解码媒体。供上游端到端测试。"""

    def __init__(
        self,
        *,
        name: str = "media_analyzer.fake",
        execution_location: str = "local",
        frame_samples: list[FrameSample] | None = None,
        audio_windows: list[AudioWindow] | None = None,
        captions: list[CaptionBBox] | None = None,
        measured_duration_ms: int = 0,
        broll_duration_ms: int = 0,
        total_video_duration_ms: int = 0,
    ) -> None:
        self.name = name
        self.execution_location = execution_location
        self._frames = list(frame_samples or [])
        self._audio = list(audio_windows or [])
        self._captions = list(captions or [])
        self._measured = measured_duration_ms
        self._broll = broll_duration_ms
        self._total_video = total_video_duration_ms

    def analyze(self, request: MediaAnalysisRequest) -> MediaAnalysisResult:
        return MediaAnalysisResult(
            status=MediaAnalyzerStatus.OK,
            provider=self.name,
            frame_samples=list(self._frames),
            audio_windows=list(self._audio),
            captions=list(self._captions),
            measured_duration_ms=self._measured,
            broll_duration_ms=self._broll,
            total_video_duration_ms=self._total_video,
        )

    def health_check(self) -> MediaAnalysisResult:
        return MediaAnalysisResult(status=MediaAnalyzerStatus.OK, provider=self.name)


__all__ = [
    "AudioWindow",
    "CaptionBBox",
    "FakeMediaAnalyzerProvider",
    "FrameSample",
    "MediaAnalysisRequest",
    "MediaAnalysisResult",
    "MediaAnalyzerErrorCode",
    "MediaAnalyzerProvider",
    "MediaAnalyzerStatus",
    "UnconfiguredMediaAnalyzerProvider",
]
