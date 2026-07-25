"""RenderRuntime + Golden Media：真实执行 VF-307 FfmpegRenderGraph（VF-307 遗留补齐）。

- `assemble_render_argv` 单元测试（无需 ffmpeg）：filter_complex 作为单 token 注入 -map 前。
- Golden Media 集成（需系统 ffmpeg，无则跳过）：同图两次渲染**逐字节可复现**；PROXY vs FINAL
  **切点 0 帧差**（结构 trim 参数一致 + 真实帧序知觉一致）——docs/implementation/54c §12 ④
  在真实媒体上的证明。全程 lavfi 合成、离线。
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from videoforge_contracts import (
    CreativeTimeline,
    FfmpegRenderGraph,
    FilterGraph,
    FilterNode,
    RationalTime,
    RationalTimeRange,
    RenderInput,
    RenderStage,
    RenderTargetKind,
    Segment,
    Track,
    TrackKind,
)
from videoforge_domain import (
    CompileConfig,
    build_render_manifest,
    compile_timeline,
    hamming,
    render_manifest_cache_key,
)
from videoforge_media_core import (
    FfmpegVideoFingerprinter,
    RenderRuntime,
    assemble_render_argv,
    sha256_file,
)

_NEEDS_FFMPEG = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="需要系统 ffmpeg"
)


# --- 纯单元：argv 组装（无需 ffmpeg）--------------------------------------

def test_assemble_injects_filter_complex_before_map_as_single_token():
    graph = FfmpegRenderGraph(
        args=["ffmpeg", "-y", "-i", "/w/a.mp4", "-map", "[v]",
              "-c:v", "libx264", "/w/out.mp4"],
        filter_complex=FilterGraph(
            nodes=[FilterNode(id="n", filter="trim",
                               params={"start": "0", "end": "2"},
                               inputs=["0:v"], outputs=["v"])],
            sinks=["v"],
        ),
        inputs=[RenderInput(asset_id="a", sha256="a" * 64, resolved_path="/w/a.mp4")],
        output_path="/w/out.mp4", target=RenderTargetKind.MP4_H264,
        tool_version="8.1.2",
    )
    argv = assemble_render_argv(graph)
    assert argv[0] != "ffmpeg"  # 二进制名已剥离
    fc = argv.index("-filter_complex")
    # -filter_complex 是单个 argv token，紧邻其后；且在 -map 之前
    assert argv[fc + 1] == "[0:v]trim=start=0:end=2[v]"
    assert fc < argv.index("-map")


def test_assemble_no_filter_when_absent():
    graph = FfmpegRenderGraph(
        args=["ffmpeg", "-i", "/w/a.mp4", "-c", "copy", "/w/out.mp4"],
        filter_complex=None,
        inputs=[RenderInput(asset_id="a", sha256="a" * 64, resolved_path="/w/a.mp4")],
        output_path="/w/out.mp4", target=RenderTargetKind.MP4_H264, tool_version="8.1.2",
    )
    argv = assemble_render_argv(graph)
    assert "-filter_complex" not in argv
    assert argv == ["-i", "/w/a.mp4", "-c", "copy", "/w/out.mp4"]


# --- Golden Media 集成 -----------------------------------------------------

def _clip(dst: Path, source: str) -> None:
    # 用 -t（mandelbrot 无 duration 选项）；testsrc 与 mandelbrot 内容显著不同，供负控。
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"{source}=size=320x240:rate=30", "-t", "5",
         "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(dst)],
        check=True,
    )


def _max_index_hamming(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, int]:
    """逐位置（时间顺序敏感）帧 dHash 最大汉明距离 + 比较帧数。"""
    n = min(len(a), len(b))
    return max((hamming(a[i], b[i]) for i in range(n)), default=99), n


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    d = tmp_path_factory.mktemp("golden")
    _clip(d / "c0.mp4", "testsrc")
    _clip(d / "c1.mp4", "mandelbrot")
    resolved = {
        "c0": (str(d / "c0.mp4"), sha256_file(d / "c0.mp4")[0]),
        "c1": (str(d / "c1.mp4"), sha256_file(d / "c1.mp4")[0]),
    }

    def timeline(order: list[str]) -> CreativeTimeline:
        def rt(v: int) -> RationalTime:
            return RationalTime(value=v, rate=30)
        segs = [
            Segment(id=f"s{i}", source_ref=ref,
                     time_range=RationalTimeRange(start=rt(0), duration=rt(60)))
            for i, ref in enumerate(order)
        ]
        return CreativeTimeline(
            id="tl-golden", rate=30, duration=rt(120),
            created_at=datetime(2026, 7, 26, tzinfo=UTC),
            tracks=[Track(id="t-v1", kind=TrackKind.V1_PRIMARY_VIDEO, segments=segs)],
        )

    def compile_graph(order: list[str], out: str, stage: RenderStage):
        tl = timeline(order)
        cfg = CompileConfig(output_path=str(d / out), allowed_input_roots=(str(d),),
                             target=RenderTargetKind.MP4_H264, stage=stage,
                             aspect_ratio="9:16")
        return tl, compile_timeline(tl, resolved, cfg, tool_version="8.1.2")

    return d, compile_graph


@_NEEDS_FFMPEG
def test_golden_render_is_byte_reproducible(env):
    d, compile_graph = env
    rr = RenderRuntime()
    r1 = rr.render(compile_graph(["c0", "c1"], "out1.mp4", RenderStage.FINAL)[1])
    r2 = rr.render(compile_graph(["c0", "c1"], "out2.mp4", RenderStage.FINAL)[1])
    # 同图两次渲染 → 逐字节可复现（golden media 最强主张）
    assert r1.output_digest == r2.output_digest
    # 结构正确：9:16 → 1080x1920；两段各 2s → 4s（真实缩放+拼接，非空操作）
    assert (r1.probe.width, r1.probe.height) == (1080, 1920)
    assert abs(r1.probe.duration_s - 4.0) < 0.1
    assert r1.probe.codec == "h264"


@_NEEDS_FFMPEG
def test_proxy_and_final_same_cut_points(env):
    d, compile_graph = env
    _, g_proxy = compile_graph(["c0", "c1"], "proxy.mp4", RenderStage.PROXY)
    _, g_final = compile_graph(["c0", "c1"], "final.mp4", RenderStage.FINAL)
    # ① 结构：trim/concat 切点滤镜节点逐一相同（仅编码段不同：crf/preset）
    assert ([(n.filter, n.params) for n in g_proxy.filter_complex.nodes]
            == [(n.filter, n.params) for n in g_final.filter_complex.nodes])

    rr = RenderRuntime()
    rp = rr.render(g_proxy)
    rf = rr.render(g_final)
    assert abs(rp.probe.duration_s - rf.probe.duration_s) < 0.05
    fp = FfmpegVideoFingerprinter()
    seq_p = fp.fingerprint(rp.output_path, every_s=0.5)
    seq_f = fp.fingerprint(rf.output_path, every_s=0.5)
    # ② 真实帧序（逐位置、顺序敏感）：proxy 与 final 每个时间点是同一帧 → 切点 0 帧差。
    #    （注意：phash_sequence_similarity 是顺序无关的集合相似度，不能证明切点位置——
    #    故这里用逐位置汉明距离。）
    pf_max, n = _max_index_hamming(seq_p, seq_f)
    assert n >= 6 and pf_max <= 6  # 实测最大=1，留编码差余量

    # ③ 负控：换段顺序（不同切点位置）→ 逐位置帧显著不同，证明该检查真能鉴别切点。
    _, g_swap = compile_graph(["c1", "c0"], "swap.mp4", RenderStage.FINAL)
    seq_s = fp.fingerprint(rr.render(g_swap).output_path, every_s=0.5)
    swap_max, _ = _max_index_hamming(seq_f, seq_s)
    assert swap_max >= 20  # 实测=35：换切点 → 逐位置帧明显不同


@_NEEDS_FFMPEG
def test_render_output_digest_feeds_manifest_cache_key(env):
    d, compile_graph = env
    tl, graph = compile_graph(["c0", "c1"], "m.mp4", RenderStage.FINAL)
    rr = RenderRuntime()
    result = rr.render(graph)
    manifest = build_render_manifest(
        tl, graph, manifest_id="rm1", stage=RenderStage.FINAL,
        created_at=datetime(2026, 7, 26, tzinfo=UTC), tool_version=result.ffmpeg_version,
        output_digest=result.output_digest,
    )
    assert manifest.output_digest == result.output_digest
    # cache key 确定 + 对工具版本敏感
    assert render_manifest_cache_key(manifest) == render_manifest_cache_key(manifest)
    bumped = manifest.model_copy(update={"tool_version": "9.0.0"})
    assert render_manifest_cache_key(bumped) != render_manifest_cache_key(manifest)
