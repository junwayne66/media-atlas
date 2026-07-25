"""Remotion 编译器：CreativeTimeline → RemotionRenderRequest（docs/modules/42 §8.3）。纯函数。

许可提示（ADR-002）：Remotion 商业授权对使用者有条款要求。本模块**只产出类型化渲染请求**——
不引 Remotion 运行时、不调用 npm/CLI。真实渲染由独立 RenderProvider 端口后置隔离，接入前需专项
许可评审通过。

覆盖：V4_CAPTIONS → CAPTIONS 组件（字幕 segment 列表 + 字体/字号 Props）、V3_INFO_CARDS → INFO_CARD
组件（模板槽位）、V5_OVERLAYS → BRAND_ANIMATION 组件。V4/V3/V5 之间可选择性 opt-in（避免一条
timeline 强制生成所有组件）。entry_component_path 与 output_path 均复用 VF-307 的 `_path_within`
段级归一化白名单——同一套安全规则，防 `..` traversal，无需 domain 内重复实现。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from videoforge_contracts import (
    CreativeTimeline,
    RemotionComposition,
    RemotionProp,
    RemotionRenderManifest,
    RemotionRenderRequest,
    Segment,
    TrackKind,
)
from videoforge_domain.ffmpeg_compiler import UnsafeInputPath, _path_within


@dataclass(frozen=True)
class RemotionCompileConfig:
    """Remotion 编译参数。entry_component_path 与 output_path 均受白名单强制。"""

    entry_component_path: str
    output_path: str
    allowed_input_roots: tuple[str, ...]
    composition: RemotionComposition
    fps: int = 30
    width: int = 1080
    height: int = 1920
    # V4/V3/V5 三个轨的开关：默认按 composition 匹配
    include_captions: bool = True
    include_info_cards: bool = True
    include_overlays: bool = False


# composition → 需要哪些轨（用于类型化 Props 组装）
_COMPOSITION_TO_TRACK_KINDS: dict[RemotionComposition, frozenset[TrackKind]] = {
    RemotionComposition.CAPTIONS: frozenset({TrackKind.V4_CAPTIONS}),
    RemotionComposition.INFO_CARD: frozenset({TrackKind.V3_INFO_CARDS}),
    RemotionComposition.DATA_CHART: frozenset({TrackKind.V3_INFO_CARDS}),
    RemotionComposition.BRAND_ANIMATION: frozenset({TrackKind.V5_OVERLAYS}),
    RemotionComposition.LOWER_THIRD: frozenset({TrackKind.V4_CAPTIONS}),
}


def _seg_ms(seg: Segment) -> tuple[int, int]:
    rate = seg.time_range.start.rate
    start_ms = int(round(seg.time_range.start.value / rate * 1000))
    end_ms = int(round((seg.time_range.start.value + seg.time_range.duration.value) / rate * 1000))
    return start_ms, end_ms


def _captions_props(timeline: CreativeTimeline) -> list[dict]:
    """CAPTIONS 组件需要的 segments：{text, start_ms, end_ms, speaker_id}。"""
    items: list[dict] = []
    for track in timeline.tracks:
        if track.kind is not TrackKind.V4_CAPTIONS:
            continue
        for seg in track.segments:
            start_ms, end_ms = _seg_ms(seg)
            entry = {"segment_id": seg.id, "start_ms": start_ms, "end_ms": end_ms}
            if seg.script_sentence_id:
                entry["script_sentence_id"] = seg.script_sentence_id
            if seg.speaker_id:
                entry["speaker_id"] = seg.speaker_id
            items.append(entry)
    return items


def _info_card_props(timeline: CreativeTimeline) -> list[dict]:
    items: list[dict] = []
    for track in timeline.tracks:
        if track.kind is not TrackKind.V3_INFO_CARDS:
            continue
        for seg in track.segments:
            start_ms, end_ms = _seg_ms(seg)
            entry = {"segment_id": seg.id, "start_ms": start_ms, "end_ms": end_ms}
            if seg.template_slot:
                entry["template_slot"] = seg.template_slot
            items.append(entry)
    return items


def _overlay_props(timeline: CreativeTimeline) -> list[dict]:
    items: list[dict] = []
    for track in timeline.tracks:
        if track.kind is not TrackKind.V5_OVERLAYS:
            continue
        for seg in track.segments:
            start_ms, end_ms = _seg_ms(seg)
            items.append({"segment_id": seg.id, "start_ms": start_ms, "end_ms": end_ms})
    return items


def compile_timeline_to_remotion(
    timeline: CreativeTimeline,
    config: RemotionCompileConfig,
    *,
    request_id: str,
    tool_version: str,
) -> RemotionRenderRequest:
    """CreativeTimeline → RemotionRenderRequest（类型化 Props；不触真实 Remotion）。"""
    # 复用 VF-307 段级归一化白名单——安全一致性
    if not _path_within(config.entry_component_path, config.allowed_input_roots):
        raise UnsafeInputPath(f"entry_component_path 越出白名单：{config.entry_component_path}")
    if not _path_within(config.output_path, config.allowed_input_roots):
        raise UnsafeInputPath(f"output_path 越出白名单：{config.output_path}")

    props: list[RemotionProp] = [
        RemotionProp(key="composition", value=config.composition.value),
        RemotionProp(key="fps", value=config.fps),
        RemotionProp(key="width", value=config.width),
        RemotionProp(key="height", value=config.height),
    ]

    if config.include_captions and TrackKind.V4_CAPTIONS in _COMPOSITION_TO_TRACK_KINDS.get(
        config.composition, frozenset()
    ):
        props.append(RemotionProp(key="captions", value=_captions_props(timeline)))
    if config.include_info_cards and TrackKind.V3_INFO_CARDS in _COMPOSITION_TO_TRACK_KINDS.get(
        config.composition, frozenset()
    ):
        props.append(RemotionProp(key="info_cards", value=_info_card_props(timeline)))
    if config.include_overlays and TrackKind.V5_OVERLAYS in _COMPOSITION_TO_TRACK_KINDS.get(
        config.composition, frozenset()
    ):
        props.append(RemotionProp(key="overlays", value=_overlay_props(timeline)))

    duration_ms = int(round(timeline.duration.value / timeline.duration.rate * 1000))

    return RemotionRenderRequest(
        id=request_id,
        timeline_id=timeline.id,
        composition=config.composition,
        props=props,
        duration_ms=duration_ms,
        fps=config.fps,
        width=config.width,
        height=config.height,
        entry_component_path=config.entry_component_path,
        output_path=config.output_path,
        tool_version=tool_version,
    )


def build_remotion_render_manifest(
    request: RemotionRenderRequest,
    *,
    manifest_id: str,
    created_at: datetime,
    tool_version: str,
    input_digests: dict[str, str] | None = None,
    output_digest: str | None = None,
) -> RemotionRenderManifest:
    return RemotionRenderManifest(
        id=manifest_id,
        request=request,
        input_digests=input_digests or {},
        output_digest=output_digest,
        tool_version=tool_version,
        created_at=created_at,
    )


def serialize_props(props: list[RemotionProp]) -> str:
    """Props → 稳定 JSON（sort_keys 保 cache key 复现，与 Python dict 顺序解耦）。"""
    payload = {p.key: p.value for p in props}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def remotion_manifest_cache_key(manifest: RemotionRenderManifest) -> str:
    """稳定 cache key：composition + tool_version + sorted digests + canonical props。"""
    request = manifest.request
    digests = "|".join(f"{k}={v}" for k, v in sorted(manifest.input_digests.items()))
    payload = "\x01".join(
        [
            request.composition.value,
            manifest.tool_version,
            request.entry_component_path,
            str(request.fps),
            str(request.width),
            str(request.height),
            str(request.duration_ms),
            digests,
            serialize_props(request.props),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "RemotionCompileConfig",
    "build_remotion_render_manifest",
    "compile_timeline_to_remotion",
    "remotion_manifest_cache_key",
    "serialize_props",
]
