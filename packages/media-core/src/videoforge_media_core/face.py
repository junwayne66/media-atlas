"""人脸检测端口 + Fake/Null（docs/modules/41 §9 Face Track）。

真实人脸检测需模型（OpenCV Haar/DNN 或 dlib），属停止条件邻域——与 ASR/OCR/VLM 一样走
Provider，真实检测器接入留到有授权模型时（VF-204 VLM 采样阶段一并处理）。本任务只落地端口
+ Null/Fake：默认 NullFaceDetector 诚实报告「未配置」（空 + configured=False），不静默假装
有结果；FakeFaceDetector 供下游（Blueprint）对接口开发。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FaceDetection:
    frame_time_s: float
    bbox: tuple[float, float, float, float]  # 归一化 x, y, w, h ∈ [0, 1]
    confidence: float


@runtime_checkable
class FaceDetector(Protocol):
    configured: bool

    def detect(self, video_path: Path) -> list[FaceDetection]:
        """检测视频中的人脸；未配置真实检测器时返回空（不假装）。"""
        ...


class NullFaceDetector:
    """默认：未接入真实检测器（需模型）。返回空 + configured=False（可诊断，非静默）。"""

    configured = False

    def detect(self, video_path: Path) -> list[FaceDetection]:
        return []


class FakeFaceDetector:
    """确定性 Fake：供下游对接口开发/测试；不做真实检测。"""

    configured = True

    def __init__(self, detections: list[FaceDetection] | None = None) -> None:
        self._detections = list(
            detections
            if detections is not None
            else [FaceDetection(frame_time_s=0.0, bbox=(0.4, 0.3, 0.2, 0.3), confidence=0.99)]
        )

    def detect(self, video_path: Path) -> list[FaceDetection]:
        return list(self._detections)
