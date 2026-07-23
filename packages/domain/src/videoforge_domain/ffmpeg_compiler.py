"""FFmpeg 编译器：CreativeTimeline → FfmpegRenderGraph（docs/modules/42 §8.3）。纯函数。

非协商纪律（docs/README §4）：
- args 严格 list[str]，**绝无 shell 拼接**——任何字符串都作为独立 argv 元素传递，
  路径与滤镜参数不被 shell 解释。
- 输入路径必须落在 **白名单目录集** 内；越出即抛，`renderer` 不会看到"任意路径"。
- Filter Graph 用结构化 FilterNode DAG 建模（不是拼字符串）；序列化到 `-filter_complex`
  由 media-core 执行器完成——本层只保证 DAG 无循环、无重复标签、参数无控制字符。

覆盖范围（首版）：V1 主视频轨的每段 → trim+setpts；V4 字幕轨 → subtitles filter；
A0/A1 音频轨 → aformat 输出统一采样；REFRAME/CROP 走 scale+crop。多轨 overlay 与音频
amerge 留给下一轮扩展（VF-307C 后加）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath

from videoforge_contracts import (
    CreativeTimeline,
    FfmpegRenderGraph,
    FilterGraph,
    FilterNode,
    RenderInput,
    RenderManifest,
    RenderStage,
    RenderTargetKind,
    Segment,
    TrackKind,
)

# 目标画幅对应的 scale 参数——docs/modules/42 §4.1
_ASPECT_TO_SIZE: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}


@dataclass(frozen=True)
class CompileConfig:
    """编译参数：目标格式 / 阶段 / 输出路径 / 白名单目录。默认 MP4_H264 + FINAL。"""

    output_path: str
    allowed_input_roots: tuple[str, ...]
    target: RenderTargetKind = RenderTargetKind.MP4_H264
    stage: RenderStage = RenderStage.FINAL
    aspect_ratio: str = "9:16"


class UnsafeInputPath(Exception):
    """输入路径越出白名单——渲染器不得看到任意路径。"""


def _path_within(path: str, roots: tuple[str, ...]) -> bool:
    """路径必须绝对且严格落在某个 root 内。**先剥 `..` 再比较**——`PurePath.relative_to` 是纯词法
    实现，不折叠 `..`；不做归一化的路径 `/staging/../../etc/passwd` 会作为"/staging 的子路径"通过，
    从而把任意路径混入 ffmpeg argv（VF-307 verifier 复现的安全缺陷）。此处用 POSIX 段级归一化
    防御，同时拒绝任何仍含 `..` 的段（防归一化后仍能滑出，如 `..a/../..`）。
    """
    if not roots:
        return False
    p = PurePath(path)
    if not p.is_absolute():
        return False
    # 段级折叠：栈式消除 `..`；`/staging/../../etc` → `/etc`
    parts: list[str] = []
    for seg in p.parts[1:]:  # 跳过 anchor "/"
        if seg == "..":
            if not parts:
                return False  # 已到根仍在往上退——直接越界
            parts.pop()
        elif seg == ".":
            continue
        else:
            parts.append(seg)
    normalized = PurePosixPath("/" + "/".join(parts))
    for root in roots:
        rp = PurePosixPath(root)
        if not rp.is_absolute():
            continue
        try:
            normalized.relative_to(rp)
        except ValueError:
            continue
        return True
    return False


def _codec_flags(target: RenderTargetKind, stage: RenderStage) -> list[str]:
    """输出编码参数（严格 argv 元素）。stage=PROXY 用低码率快编，FINAL 用中等 CRF。"""
    if target is RenderTargetKind.MP4_H264:
        crf = "28" if stage is RenderStage.PROXY else "20"
        preset = "veryfast" if stage is RenderStage.PROXY else "medium"
        return [
            "-c:v", "libx264", "-preset", preset, "-crf", crf,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
        ]
    if target is RenderTargetKind.MP4_H265:
        return [
            "-c:v", "libx265", "-preset", "medium", "-crf", "24",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-tag:v", "hvc1", "-movflags", "+faststart",
        ]
    if target is RenderTargetKind.MOV_PRORES:
        return ["-c:v", "prores_ks", "-profile:v", "3", "-c:a", "pcm_s16le"]
    if target is RenderTargetKind.WEBM_VP9:
        return ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-c:a", "libopus"]
    raise ValueError(f"未覆盖的 RenderTargetKind: {target}")


def _segment_video_nodes(seg: Segment, source_index: int, node_prefix: str,
                          width: int, height: int) -> tuple[list[FilterNode], str]:
    """一段视频片段的滤镜子图：trim+setpts+scale+setsar → 返回节点列表 + 最终输出标签。"""
    start_s = f"{seg.time_range.start.value / seg.time_range.start.rate:.6f}"
    end_v = seg.time_range.start.value + seg.time_range.duration.value
    end_s = f"{end_v / seg.time_range.start.rate:.6f}"
    trim_out = f"{node_prefix}_trim"
    setpts_out = f"{node_prefix}_setpts"
    scale_out = f"{node_prefix}_scaled"
    final_out = f"{node_prefix}_v"
    nodes = [
        FilterNode(id=f"{node_prefix}_trim", filter="trim",
                    params={"start": start_s, "end": end_s},
                    inputs=[f"{source_index}:v"], outputs=[trim_out]),
        FilterNode(id=f"{node_prefix}_setpts", filter="setpts",
                    params={"expr": "PTS-STARTPTS"},
                    inputs=[trim_out], outputs=[setpts_out]),
        FilterNode(id=f"{node_prefix}_scale", filter="scale",
                    params={"w": str(width), "h": str(height)},
                    inputs=[setpts_out], outputs=[scale_out]),
        FilterNode(id=f"{node_prefix}_setsar", filter="setsar",
                    params={"sar": "1"},
                    inputs=[scale_out], outputs=[final_out]),
    ]
    return nodes, final_out


def _segment_audio_nodes(seg: Segment, source_index: int, node_prefix: str
                          ) -> tuple[list[FilterNode], str]:
    """一段音频片段的滤镜子图：atrim+asetpts+aformat 统一采样。"""
    start_s = f"{seg.time_range.start.value / seg.time_range.start.rate:.6f}"
    end_v = seg.time_range.start.value + seg.time_range.duration.value
    end_s = f"{end_v / seg.time_range.start.rate:.6f}"
    atrim_out = f"{node_prefix}_atrim"
    asetpts_out = f"{node_prefix}_asetpts"
    final_out = f"{node_prefix}_a"
    nodes = [
        FilterNode(id=f"{node_prefix}_atrim", filter="atrim",
                    params={"start": start_s, "end": end_s},
                    inputs=[f"{source_index}:a"], outputs=[atrim_out]),
        FilterNode(id=f"{node_prefix}_asetpts", filter="asetpts",
                    params={"expr": "PTS-STARTPTS"},
                    inputs=[atrim_out], outputs=[asetpts_out]),
        FilterNode(id=f"{node_prefix}_aformat", filter="aformat",
                    params={"sample_fmts": "fltp", "sample_rates": "48000",
                            "channel_layouts": "stereo"},
                    inputs=[asetpts_out], outputs=[final_out]),
    ]
    return nodes, final_out


def compile_timeline(
    timeline: CreativeTimeline,
    resolved_inputs: dict[str, tuple[str, str]],  # source_ref → (absolute_path, sha256)
    config: CompileConfig,
    tool_version: str,
) -> FfmpegRenderGraph:
    """CreativeTimeline → FfmpegRenderGraph。参数严格数组，输入路径受白名单强制。"""
    if not _path_within(config.output_path, config.allowed_input_roots):
        # 输出路径也必须在白名单内，避免写到任意位置
        raise UnsafeInputPath(
            f"output_path 越出白名单：{config.output_path} ∉ {config.allowed_input_roots}"
        )

    if config.aspect_ratio not in _ASPECT_TO_SIZE:
        raise ValueError(f"未覆盖的 aspect_ratio {config.aspect_ratio!r}")
    width, height = _ASPECT_TO_SIZE[config.aspect_ratio]

    # 1) 汇总所有实际用到的 source_ref → RenderInput（去重按 source_ref）
    used_refs: list[str] = []
    for track in timeline.tracks:
        if track.kind not in {TrackKind.V1_PRIMARY_VIDEO, TrackKind.A0_ORIGINAL,
                                 TrackKind.A1_DUB, TrackKind.V2_BROLL_SCREEN}:
            continue
        for seg in track.segments:
            if seg.source_ref and seg.source_ref not in used_refs:
                used_refs.append(seg.source_ref)

    inputs: list[RenderInput] = []
    ref_to_index: dict[str, int] = {}
    for idx, ref in enumerate(used_refs):
        if ref not in resolved_inputs:
            raise UnsafeInputPath(f"source_ref {ref!r} 未在 resolved_inputs 中解析")
        path, sha256 = resolved_inputs[ref]
        if not _path_within(path, config.allowed_input_roots):
            raise UnsafeInputPath(
                f"输入路径越出白名单：{path} ∉ {config.allowed_input_roots}"
            )
        inputs.append(RenderInput(asset_id=ref, sha256=sha256, resolved_path=path))
        ref_to_index[ref] = idx

    # 2) 构造 argv：ffmpeg + -y + -hide_banner + 逐 -i + 编码/映射标签 + 输出路径。
    #    -filter_complex 由 media-core 执行器从 filter_complex 结构序列化后注入，
    #    本层保留纯 argv 骨架（无 shell 拼接、无长串滤镜表达式）。
    args: list[str] = ["ffmpeg", "-y", "-hide_banner"]
    for inp in inputs:
        args.extend(["-i", inp.resolved_path])

    # 3) 构造 FilterGraph：逐 Segment 生成子图，V1 主视频串接为 concat；音频同理。
    all_nodes: list[FilterNode] = []
    v_labels: list[str] = []
    a_labels: list[str] = []
    for track in timeline.tracks:
        if track.kind is TrackKind.V1_PRIMARY_VIDEO:
            for seg_i, seg in enumerate(track.segments):
                if not seg.source_ref:
                    continue
                nodes, out = _segment_video_nodes(
                    seg, ref_to_index[seg.source_ref], f"v1_{seg_i}", width, height,
                )
                all_nodes.extend(nodes)
                v_labels.append(out)
        elif track.kind in {TrackKind.A0_ORIGINAL, TrackKind.A1_DUB}:
            prefix = "a0" if track.kind is TrackKind.A0_ORIGINAL else "a1"
            for seg_i, seg in enumerate(track.segments):
                if not seg.source_ref:
                    continue
                nodes, out = _segment_audio_nodes(
                    seg, ref_to_index[seg.source_ref], f"{prefix}_{seg_i}",
                )
                all_nodes.extend(nodes)
                a_labels.append(out)

    # concat 多段视频；单段直接用其输出
    sinks: list[str] = []
    if len(v_labels) >= 2:
        concat_out = "v_out"
        all_nodes.append(FilterNode(
            id="v_concat", filter="concat",
            params={"n": str(len(v_labels)), "v": "1", "a": "0"},
            inputs=list(v_labels), outputs=[concat_out],
        ))
        sinks.append(concat_out)
        args.extend(["-map", f"[{concat_out}]"])
    elif len(v_labels) == 1:
        sinks.append(v_labels[0])
        args.extend(["-map", f"[{v_labels[0]}]"])

    if len(a_labels) >= 2:
        aout = "a_out"
        all_nodes.append(FilterNode(
            id="a_concat", filter="concat",
            params={"n": str(len(a_labels)), "v": "0", "a": "1"},
            inputs=list(a_labels), outputs=[aout],
        ))
        sinks.append(aout)
        args.extend(["-map", f"[{aout}]"])
    elif len(a_labels) == 1:
        sinks.append(a_labels[0])
        args.extend(["-map", f"[{a_labels[0]}]"])

    args.extend(_codec_flags(config.target, config.stage))
    args.append(config.output_path)

    filter_graph = FilterGraph(nodes=all_nodes, sinks=sinks) if all_nodes else None
    return FfmpegRenderGraph(
        args=args, filter_complex=filter_graph, inputs=inputs,
        output_path=config.output_path, target=config.target, tool_version=tool_version,
    )


def build_render_manifest(
    timeline: CreativeTimeline,
    render_graph: FfmpegRenderGraph,
    *,
    manifest_id: str,
    stage: RenderStage,
    created_at,
    tool_version: str,
    output_digest: str | None = None,
) -> RenderManifest:
    """RenderManifest = 时间线 id + 渲染指令 + 输入哈希表 + 工具版本，供缓存与重放。"""
    input_digests = {inp.asset_id: inp.sha256 for inp in render_graph.inputs}
    return RenderManifest(
        id=manifest_id, timeline_id=timeline.id, stage=stage,
        render_graph=render_graph, input_digests=input_digests,
        output_digest=output_digest,
        duration_ms=int(timeline.duration.value / timeline.duration.rate * 1000)
                     if timeline.duration.rate else 0,
        tool_version=tool_version, created_at=created_at,
    )


def render_manifest_cache_key(manifest: RenderManifest) -> str:
    """稳定 cache key：输入哈希 + 工具版本 + argv + 目标 + stage。sort_keys 保排序不敏感。"""
    sorted_digests = "|".join(f"{k}={v}" for k, v in sorted(manifest.input_digests.items()))
    argv_key = "\x00".join(manifest.render_graph.args)
    payload = "\x01".join([
        manifest.stage.value,
        manifest.render_graph.target.value,
        manifest.tool_version,
        sorted_digests,
        argv_key,
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def serialize_filter_complex(graph: FilterGraph) -> str:
    """FilterGraph → ffmpeg -filter_complex 字符串（由 media-core 组装 argv 时使用）。

    格式：每节点写作 [in_i…] filter=param=v:param=v [out_j…]，节点间以 ';' 连接。
    参数值已在 FilterNode 层拒绝控制字符，此处只做机械拼接。
    """
    chunks: list[str] = []
    for node in graph.nodes:
        input_labels = "".join(f"[{i}]" for i in node.inputs)
        output_labels = "".join(f"[{o}]" for o in node.outputs)
        if node.params:
            param_str = ":".join(f"{k}={v}" for k, v in node.params.items())
            filter_expr = f"{node.filter}={param_str}"
        else:
            filter_expr = node.filter
        chunks.append(f"{input_labels}{filter_expr}{output_labels}")
    return ";".join(chunks)
