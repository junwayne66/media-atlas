"""真实视频指纹集成测试：同内容不同转码聚入同 duplicate group（验收 41 §13）。

需系统 ffmpeg；无则跳过（CI 的 macOS runner 属预期跳过）。用 lavfi 合成媒体，全程离线。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from videoforge_domain import AssetFingerprint, DuplicateLayer, find_duplicate_groups
from videoforge_media_core import FfmpegVideoFingerprinter

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="需要系统 ffmpeg")


def _encode(dst: Path, *, source: str, size: str, crf: str, preset: str) -> None:
    subprocess.run(
        [
            "ffmpeg", "-v", "error",
            "-f", "lavfi", "-i", f"{source}=size={size}:rate=30",
            "-t", "6", "-c:v", "libx264", "-crf", crf, "-preset", preset,
            str(dst),
        ],
        check=True,
    )


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> tuple[Path, Path, Path]:
    d = tmp_path_factory.mktemp("fp")
    a, b, other = d / "a.mp4", d / "b.mp4", d / "other.mp4"
    # 同内容 testsrc：不同分辨率 + 不同码率/preset（真实转码差异）
    _encode(a, source="testsrc", size="320x240", crf="20", preset="ultrafast")
    _encode(b, source="testsrc", size="480x360", crf="32", preset="veryfast")
    # 不同内容
    _encode(other, source="mandelbrot", size="320x240", crf="20", preset="ultrafast")
    return a, b, other


def test_transcodes_of_same_video_group_together(clips) -> None:
    a, b, other = clips
    fp = FfmpegVideoFingerprinter()
    seq_a = fp.fingerprint(a, every_s=1.0)
    seq_b = fp.fingerprint(b, every_s=1.0)
    seq_o = fp.fingerprint(other, every_s=1.0)
    assert len(seq_a) >= 3  # 6 秒 / 1 秒 应抽到多帧

    fps = [
        AssetFingerprint("a", "sha_a", video_phashes=seq_a),
        AssetFingerprint("b", "sha_b", video_phashes=seq_b),
        AssetFingerprint("o", "sha_o", video_phashes=seq_o),
    ]
    groups = find_duplicate_groups(fps)
    assert len(groups) == 1  # 只有 a/b 一组
    assert set(groups[0].member_asset_ids) == {"a", "b"}  # 两转码聚同组
    assert DuplicateLayer.VIDEO in groups[0].layers
    # "o"（不同内容）未进任何组


def test_fingerprint_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        FfmpegVideoFingerprinter().fingerprint(Path("/no/such/file.mp4"))
