"""ffprobe 媒体探测：参数数组执行，禁 shell 字符串（AGENTS.md 规则 7）。"""

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Protocol

from videoforge_contracts import MediaProbe


class ProbeProvider(Protocol):
    def probe(self, path: Path) -> MediaProbe: ...


class FfprobeNotAvailable(RuntimeError):
    pass


class FfprobeProbeProvider:
    def __init__(self, binary: str | None = None) -> None:
        resolved = binary or shutil.which("ffprobe")
        if resolved is None:
            raise FfprobeNotAvailable("找不到 ffprobe；请安装 FFmpeg 或显式传入路径")
        self._binary = resolved

    def probe(self, path: Path) -> MediaProbe:
        if not path.is_file():
            raise FileNotFoundError(path)
        result = subprocess.run(
            [
                self._binary,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
        audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

        fps: float | None = None
        if video is not None:
            rate = video.get("avg_frame_rate") or video.get("r_frame_rate")
            if rate and rate not in {"0/0", "N/A"}:
                fps = float(Fraction(rate))

        return MediaProbe(
            duration_s=float(fmt["duration"]) if fmt.get("duration") else None,
            fps=fps,
            width=video.get("width") if video else None,
            height=video.get("height") if video else None,
            channels=audio.get("channels") if audio else None,
            codec=video.get("codec_name")
            if video
            else (audio.get("codec_name") if audio else None),
            time_base=video.get("time_base") if video else None,
        )
