"""媒体运行时集成测试（真实 ffmpeg，无则跳过）：proxy/audio/scene 真实产出 + 可重放 manifest。

用 lavfi 合成媒体：6 秒片段在 3 秒处硬切（testsrc→mandelbrot）+ 440Hz 音轨，全程离线。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from videoforge_media_core.media_runtime import FfmpegRuntime

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="需要系统 ffmpeg/ffprobe",
)


@pytest.fixture(scope="module")
def source(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("mr") / "src.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x480:rate=30:duration=3",
            "-t",
            "3",
            "-f",
            "lavfi",
            "-i",
            "mandelbrot=size=640x480:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture(scope="module")
def runtime() -> FfmpegRuntime:
    return FfmpegRuntime()


def test_runtime_captures_tool_versions(runtime) -> None:
    assert runtime.ffmpeg_version and runtime.ffmpeg_version != "unknown"
    assert runtime.ffprobe_version


def test_make_proxy_720p_preserves_duration(runtime, source, tmp_path) -> None:
    result = runtime.make_proxy(source, tmp_path / "proxy.mp4")
    assert result.artifact_path.is_file()
    assert result.probe.height == 720  # 720p 预览
    assert abs((result.probe.duration_s or 0) - 6.0) < 0.3  # 保持时长
    m = result.manifest
    assert m.op == "media.proxy.ffmpeg"
    assert m.tool == "ffmpeg" and m.tool_version == runtime.ffmpeg_version  # 工具版本入 manifest
    assert len(m.inputs) == 1 and len(m.outputs) == 1  # 输入/输出哈希都在
    assert m.inputs[0] != m.outputs[0]


def test_extract_audio_48k_mono(runtime, source, tmp_path) -> None:
    result = runtime.extract_audio(source, tmp_path / "a.wav")
    assert result.artifact_path.is_file()
    probe = runtime.probe(result.artifact_path)
    assert probe.channels == 1  # 单声道
    assert probe.codec == "pcm_s16le"  # WAV PCM
    assert result.manifest.op == "media.audio.ffmpeg"
    assert result.manifest.config["sample_rate"] == 48000


def test_detect_scenes_finds_the_cut(runtime, source) -> None:
    result = runtime.detect_scenes(source, threshold=0.3)
    # 3 秒处 testsrc→mandelbrot 硬切应被检出
    assert any(2.5 < c < 3.5 for c in result.cuts), result.cuts
    assert result.manifest.op == "media.scene.ffmpeg"
    assert result.manifest.outputs == ()  # 分析型操作无输出产物


def test_manifest_is_replayable(runtime, source, tmp_path) -> None:
    a = runtime.make_proxy(source, tmp_path / "p1.mp4")
    b = runtime.make_proxy(source, tmp_path / "p2.mp4")
    # 同输入同配置 → 同 cache key（可命中缓存避免重复计算）
    assert a.manifest.cache_key == b.manifest.cache_key
    # 输出内容一致（确定性编码参数）→ 输出哈希也相同
    assert a.manifest.outputs == b.manifest.outputs


def test_missing_source_raises(runtime, tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        runtime.make_proxy(Path("/no/such.mp4"), tmp_path / "x.mp4")


def test_corrupt_input_raises_media_runtime_error(runtime, tmp_path) -> None:
    from videoforge_media_core import MediaRuntimeError

    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"\x00" * 4096)  # 不是有效媒体
    # 三操作对损坏输入都抛统一 MediaRuntimeError（含 detect_scenes，不外泄裸 CalledProcessError）
    with pytest.raises(MediaRuntimeError):
        runtime.make_proxy(bad, tmp_path / "p.mp4")
    with pytest.raises(MediaRuntimeError):
        runtime.extract_audio(bad, tmp_path / "a.wav")
    with pytest.raises(MediaRuntimeError):
        runtime.detect_scenes(bad)
