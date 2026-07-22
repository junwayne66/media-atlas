"""真实视频指纹：ffmpeg 抽帧 → dHash 序列（docs/modules/41 §5/§6 ProbeMedia/Fingerprint）。

参数数组执行 ffmpeg（禁 shell 字符串，README §4 规则）：按固定间隔抽帧、缩到
(hash_size+1)x hash_size 灰度、rawvideo 输出，逐帧套 domain 的纯 dhash_from_gray。
dHash 在 9x8 灰度上比较——与源分辨率/码率无关，故同内容不同转码得近乎相同的序列。

音频声纹指纹（Chromaprint/fpcalc）本机未装，延后（third_party_manifest 已记为待接工具）。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from videoforge_domain import dhash_from_gray

_DEFAULT_HASH_SIZE = 8
_DEFAULT_EVERY_S = 2.0


class VideoFingerprinter(Protocol):
    def fingerprint(self, path: Path, *, every_s: float = _DEFAULT_EVERY_S) -> tuple[int, ...]: ...


class FfmpegNotAvailable(RuntimeError):
    pass


class FfmpegVideoFingerprinter:
    """用 ffmpeg 抽帧算 dHash 序列。须存在 ffmpeg 二进制。"""

    def __init__(self, binary: str | None = None, *, hash_size: int = _DEFAULT_HASH_SIZE) -> None:
        resolved = binary or shutil.which("ffmpeg")
        if resolved is None:
            raise FfmpegNotAvailable("找不到 ffmpeg；请安装 FFmpeg 或显式传入路径")
        self._binary = resolved
        self._hash_size = hash_size

    def fingerprint(self, path: Path, *, every_s: float = _DEFAULT_EVERY_S) -> tuple[int, ...]:
        if not path.is_file():
            raise FileNotFoundError(path)
        if every_s <= 0:
            raise ValueError("every_s 必须 > 0")
        w, h = self._hash_size + 1, self._hash_size
        rate = 1.0 / every_s
        result = subprocess.run(
            [
                self._binary,
                "-v",
                "error",
                "-i",
                str(path),
                "-vf",
                f"fps={rate:.6f},scale={w}:{h}:flags=area,format=gray",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "gray",
                "-",
            ],
            capture_output=True,
            timeout=180,
            check=True,
        )
        raw = result.stdout
        frame_bytes = w * h
        hashes: list[int] = []
        for off in range(0, len(raw) - frame_bytes + 1, frame_bytes):
            frame = raw[off : off + frame_bytes]
            hashes.append(dhash_from_gray(w, h, frame, hash_size=self._hash_size))
        return tuple(hashes)
