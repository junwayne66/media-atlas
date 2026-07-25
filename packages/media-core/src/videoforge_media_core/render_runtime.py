"""渲染运行时：执行 VF-307 编译出的 `FfmpegRenderGraph`（真实 ffmpeg 子进程）。

VF-307 的 domain 编译器把 CreativeTimeline 编成结构化的 `FfmpegRenderGraph`——`args` 是经
metachar 校验的纯 argv 骨架，**故意不含** `-filter_complex` 长串（滤镜表达式合法含 `;,[]`，
不能进 metachar 白名单）。本层是执行器：把 `filter_complex` 结构序列化成**单个 argv token**
在 `-map` 前注入，走 args-array 子进程（无 shell、无注入面，README §4），产出真实成片 +
输出 sha256 + ffprobe 探测。

media-core → domain 依赖合法（domain 是纯下层；video_fingerprint 已有先例）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from videoforge_contracts import FfmpegRenderGraph, MediaProbe
from videoforge_domain import serialize_filter_complex
from videoforge_media_core.errors import MediaRuntimeError
from videoforge_media_core.hashing import sha256_file
from videoforge_media_core.media_runtime import FfmpegRuntime


def assemble_render_argv(graph: FfmpegRenderGraph) -> list[str]:
    """`FfmpegRenderGraph` → 完整 ffmpeg 参数（**不含二进制名**）。

    - `args[0] == "ffmpeg"` 去掉（执行器补真实二进制路径）。
    - 有 `filter_complex` 时，序列化成一个字符串，作为**单个 argv token** 在第一个 `-map`
      前注入（`-filter_complex <str>`）；无 `-map` 时插在输出路径（末元素）前。
    - 该字符串合法含 `;` `,` `[]` `:` 等——它是一个 argv 元素，永不经 shell（README §4）。
    """
    args = list(graph.args)
    if args and args[0] == "ffmpeg":
        args = args[1:]
    if graph.filter_complex is not None and graph.filter_complex.nodes:
        serialized = serialize_filter_complex(graph.filter_complex)
        try:
            insert_at = args.index("-map")
        except ValueError:
            insert_at = max(len(args) - 1, 0)
        args[insert_at:insert_at] = ["-filter_complex", serialized]
    return args


@dataclass(frozen=True)
class RenderResult:
    """一次渲染的产出事实。output_digest 是真实成片 sha256（可放入 RenderManifest 复现）。"""

    output_path: Path
    output_digest: str
    probe: MediaProbe
    ffmpeg_version: str
    argv: tuple[str, ...]  # 实际执行的参数（不含二进制名），供审计/复现


class RenderRuntime:
    """执行 `FfmpegRenderGraph` → 真实成片 + 输出哈希 + 探测。须存在 ffmpeg/ffprobe。"""

    def __init__(self, *, ffmpeg: str | None = None, ffprobe: str | None = None) -> None:
        self._rt = FfmpegRuntime(ffmpeg=ffmpeg, ffprobe=ffprobe)
        self.ffmpeg_version = self._rt.ffmpeg_version

    def render(self, graph: FfmpegRenderGraph) -> RenderResult:
        """执行渲染图，返回成片路径 + sha256 + 探测。输入缺失/未产出 → MediaRuntimeError。"""
        for inp in graph.inputs:
            if not Path(inp.resolved_path).is_file():
                raise MediaRuntimeError(f"渲染输入文件不存在：{inp.resolved_path}")
        argv = assemble_render_argv(graph)
        self._rt.run(argv)
        out = Path(graph.output_path)
        if not out.is_file():
            raise MediaRuntimeError(f"渲染未产出文件：{out}")
        digest, _ = sha256_file(out)
        return RenderResult(
            output_path=out,
            output_digest=digest,
            probe=self._rt.probe(out),
            ffmpeg_version=self.ffmpeg_version,
            argv=tuple(argv),
        )
