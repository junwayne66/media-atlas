"""人脸检测端口：Null 诚实报未配置、Fake 确定性；真实检测器（需模型）延后。"""

from pathlib import Path

from videoforge_media_core.face import (
    FaceDetection,
    FaceDetector,
    FakeFaceDetector,
    NullFaceDetector,
)

_PATH = Path("/tmp/clip.mp4")


def test_null_detector_reports_unconfigured_not_silent() -> None:
    det = NullFaceDetector()
    assert det.configured is False  # 明确「未配置」，可诊断
    assert det.detect(_PATH) == []
    assert isinstance(det, FaceDetector)  # 满足端口协议


def test_fake_detector_is_deterministic() -> None:
    det = FakeFaceDetector()
    assert det.configured is True
    a, b = det.detect(_PATH), det.detect(_PATH)
    assert a == b and len(a) == 1
    assert 0.0 <= a[0].bbox[0] <= 1.0 and a[0].confidence == 0.99
    assert isinstance(det, FaceDetector)


def test_fake_detector_accepts_custom_detections() -> None:
    custom = [FaceDetection(1.5, (0.1, 0.1, 0.2, 0.2), 0.8)]
    assert FakeFaceDetector(custom).detect(_PATH) == custom
