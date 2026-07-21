import shutil
import subprocess

import pytest

from videoforge_media_core import FfprobeProbeProvider

pytestmark = pytest.mark.skipif(
    shutil.which("ffprobe") is None or shutil.which("ffmpeg") is None,
    reason="需要系统 ffmpeg/ffprobe",
)


@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory):
    """1 秒 320x240 合成视频 + 静音音轨（50 §12：小型合成媒体 fixture）。"""
    path = tmp_path_factory.mktemp("media") / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return path


def test_probe_reports_media_attributes(synthetic_video) -> None:
    probe = FfprobeProbeProvider().probe(synthetic_video)
    assert probe.duration_s == pytest.approx(1.0, abs=0.2)
    assert probe.width == 320
    assert probe.height == 240
    assert probe.fps == pytest.approx(30.0, abs=0.5)
    assert probe.channels == 2
    assert probe.codec == "h264"


def test_probe_missing_file_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        FfprobeProbeProvider().probe(tmp_path / "nope.mp4")
