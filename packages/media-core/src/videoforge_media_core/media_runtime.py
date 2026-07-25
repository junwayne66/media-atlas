"""媒体运行时（docs/modules/41 §3 ProbeMedia/NormalizeInput、§9 镜头、§11 缓存）。

FFmpeg/ffprobe 以参数数组子进程执行（禁 shell 字符串、无注入面，README §4 规则）；
每个操作产出可重放 JobManifest（输入哈希 + 工具版本 + 输出哈希）。工具版本探测并入 manifest。

真实操作（本机 ffmpeg 可用）：probe / make_proxy（720p 预览）/ extract_audio（48kHz WAV
供 ASR）/ detect_scenes（场景切点）。Face/运动的运动强度基础特征由场景检测副产；真实人脸
检测需模型，走 FaceDetector 端口 + Fake 延后（见 face.py）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoforge_contracts import MediaProbe
from videoforge_media_core.errors import FfmpegNotAvailable, MediaRuntimeError
from videoforge_media_core.hashing import sha256_file
from videoforge_media_core.job_manifest import MANIFEST_SCHEMA_VERSION, JobManifest
from videoforge_media_core.probe import FfprobeProbeProvider

_PTS_TIME = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


@dataclass(frozen=True)
class ProxyResult:
    artifact_path: Path
    manifest: JobManifest
    probe: MediaProbe


@dataclass(frozen=True)
class AudioResult:
    artifact_path: Path
    manifest: JobManifest


@dataclass(frozen=True)
class SceneResult:
    cuts: tuple[float, ...]  # 场景切点时间戳（秒）
    manifest: JobManifest


def _tool_version(binary: str, name: str) -> str:
    out = subprocess.run(
        [binary, "-version"], capture_output=True, text=True, timeout=30, check=True
    ).stdout
    first = out.splitlines()[0] if out else ""
    parts = first.split()
    # "ffmpeg version 8.1.2 Copyright..." → 8.1.2
    if len(parts) >= 3 and parts[0] == name and parts[1] == "version":
        return parts[2]
    return first or "unknown"


class FfmpegRuntime:
    """基于 ffmpeg/ffprobe 的媒体运行时。须存在二进制；版本在构造时探测。"""

    def __init__(self, *, ffmpeg: str | None = None, ffprobe: str | None = None) -> None:
        ffmpeg_bin = ffmpeg or shutil.which("ffmpeg")
        ffprobe_bin = ffprobe or shutil.which("ffprobe")
        if ffmpeg_bin is None or ffprobe_bin is None:
            raise FfmpegNotAvailable("找不到 ffmpeg/ffprobe；请安装 FFmpeg 或显式传入路径")
        self._ffmpeg = ffmpeg_bin
        self._ffprobe = ffprobe_bin
        self.ffmpeg_version = _tool_version(ffmpeg_bin, "ffmpeg")
        self.ffprobe_version = _tool_version(ffprobe_bin, "ffprobe")
        self._prober = FfprobeProbeProvider(ffprobe_bin)

    def _run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self._ffmpeg, *argv], capture_output=True, text=True, timeout=600, check=True
            )
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or "").strip().splitlines()[-1:] or [""]
            raise MediaRuntimeError(f"ffmpeg 失败：{tail[0]}") from exc

    def _manifest(
        self, op: str, src: Path, config: dict[str, Any], out: Path | None
    ) -> JobManifest:
        in_digest, _ = sha256_file(src)
        outputs: tuple[str, ...] = ()
        if out is not None:
            out_digest, _ = sha256_file(out)
            outputs = (out_digest,)
        return JobManifest(
            op=op,
            schema_version=MANIFEST_SCHEMA_VERSION,
            inputs=(in_digest,),
            tool="ffmpeg",
            tool_version=self.ffmpeg_version,
            config=config,
            outputs=outputs,
            created_at=datetime.now(UTC),
        )

    def run(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        """执行一段**预校验**的 ffmpeg 参数数组（无 shell、无注入面）；供 RenderRuntime 执行
        FfmpegRenderGraph。失败统一包成 MediaRuntimeError。"""
        return self._run(argv)

    def probe(self, path: Path) -> MediaProbe:
        return self._prober.probe(path)

    def make_proxy(
        self,
        src: Path,
        dst: Path,
        *,
        height: int = 720,
        crf: int = 28,
        preset: str = "veryfast",
    ) -> ProxyResult:
        """生成 720p 低码率预览代理（保持准确时长/时基，不覆盖原文件）。"""
        if not src.is_file():
            raise FileNotFoundError(src)
        config = {"height": height, "crf": crf, "preset": preset, "vcodec": "libx264"}
        self._run(
            [
                "-v",
                "error",
                "-y",
                "-i",
                str(src),
                "-vf",
                f"scale=-2:{height}",
                "-c:v",
                "libx264",
                "-crf",
                str(crf),
                "-preset",
                preset,
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(dst),
            ]
        )
        return ProxyResult(
            artifact_path=dst,
            manifest=self._manifest("media.proxy.ffmpeg", src, config, dst),
            probe=self._prober.probe(dst),
        )

    def extract_audio(
        self,
        src: Path,
        dst: Path,
        *,
        sample_rate: int = 48000,
        channels: int = 1,
    ) -> AudioResult:
        """抽取 48kHz WAV（供 ASR/分析；不在各模块重复解码 MP4）。"""
        if not src.is_file():
            raise FileNotFoundError(src)
        config = {"sample_rate": sample_rate, "channels": channels, "codec": "pcm_s16le"}
        self._run(
            [
                "-v",
                "error",
                "-y",
                "-i",
                str(src),
                "-vn",
                "-ac",
                str(channels),
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                str(dst),
            ]
        )
        return AudioResult(
            artifact_path=dst,
            manifest=self._manifest("media.audio.ffmpeg", src, config, dst),
        )

    def detect_scenes(self, src: Path, *, threshold: float = 0.4) -> SceneResult:
        """场景切点检测（内容切换）。select 场景分 + metadata 打印切点时间戳到 stdout。"""
        if not src.is_file():
            raise FileNotFoundError(src)
        config = {"threshold": threshold, "method": "select_scene"}
        # 走 _run（capture_output 带 stdout，且把 CalledProcessError 统一包成 MediaRuntimeError）
        result = self._run(
            [
                "-v",
                "error",
                "-i",
                str(src),
                "-vf",
                f"select='gt(scene,{threshold})',metadata=print:file=-",
                "-an",
                "-f",
                "null",
                "-",
            ]
        )
        cuts = tuple(sorted(float(m) for m in _PTS_TIME.findall(result.stdout)))
        return SceneResult(
            cuts=cuts,
            manifest=self._manifest("media.scene.ffmpeg", src, config, None),
        )
