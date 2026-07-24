"""NLE 交换格式 Exporter（docs/modules/42 §10）。纯函数（除 write_* 外）。

写文件的辅助函数（write_otio_file / write_fcpxml_file / write_jianying_package）在同一模块，
以便对上层保持"一次调用产出一份完整交换资产"的语义。为避免 domain 引入 pip 依赖：
- **OTIO 文件是纯 JSON**（OTIO_SCHEMA 序列化），直接用 stdlib json 写；opentimelineio 官方读者
  能读回相同的 dict 结构（VF-306 to_otio_mapping 与 OTIO_SCHEMA 完全一致）。
- **FCPXML** 用 stdlib xml.etree 写；Apple 公开规范，无需 pip 包。
- **JianYing / CapCut Draft** 商业协议格式，新版加密：本模块产出"包+README 说明"作 fallback
  （§10 底线：导出失败不影响 MP4 最终渲染），不阻断发布链路。

所有 output_path 均走 VF-307 的 `_path_within` 段级归一化白名单——同一套 `..` traversal 防御。
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from videoforge_contracts import (
    CreativeTimeline,
    ExportEntry,
    ExporterKind,
    ExporterReport,
    ExporterStatus,
)
from videoforge_domain.ffmpeg_compiler import UnsafeInputPath, _path_within
from videoforge_domain.timeline import to_otio_mapping

_OTIO_WRITER_VERSION = "videoforge.otio.writer@0.1.0"
_FCPXML_WRITER_VERSION = "videoforge.fcpxml.writer@0.1.0"
_JIANYING_WRITER_VERSION = "videoforge.jianying.writer@0.1.0-experimental"
_CAPCUT_WRITER_VERSION = "videoforge.capcut.writer@0.1.0-experimental"


# 与 VF-307/VF-308 一致的 shell 元字符集，纵深防御
_SHELL_META_CHARS = frozenset(";|&<>`$\\\"'\n\r\t")


def _guard_output_path(path: str, allowed_roots: tuple[str, ...]) -> Path:
    """所有 writer 共用的路径护栏：绝对路径 + 白名单 + `..` 折叠归一化 + shell 元字符前置拒。

    元字符检查在写盘之前进行——否则 ExportEntry 契约验证在写盘之后才失败，会留下报告说
    FAILED 但磁盘上有以元字符命名的文件（verifier 观察 1）。
    """
    if any(c in _SHELL_META_CHARS for c in path):
        offenders = sorted({c for c in path if c in _SHELL_META_CHARS})
        raise UnsafeInputPath(
            f"output_path 含不允许的 shell 元字符 {offenders!r}：{path}"
        )
    if not _path_within(path, allowed_roots):
        raise UnsafeInputPath(f"output_path 越出白名单：{path} ∉ {allowed_roots}")
    return Path(path)


# —— OTIO：纯 JSON 写文件 ——


def write_otio_file(
    timeline: CreativeTimeline, output_path: str, *, allowed_roots: tuple[str, ...],
) -> ExportEntry:
    """CreativeTimeline → OTIO JSON 文件。opentimelineio 官方读者能读回同 dict 结构。"""
    try:
        target = _guard_output_path(output_path, allowed_roots)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = to_otio_mapping(timeline)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        target.write_text(text, encoding="utf-8")
        return ExportEntry(
            kind=ExporterKind.OTIO_FILE, status=ExporterStatus.OK,
            output_path=str(target), tool_version=_OTIO_WRITER_VERSION,
            bytes_written=len(text.encode("utf-8")),
        )
    except UnsafeInputPath:
        raise  # 安全违规直接抛，不降级
    except Exception as exc:  # noqa: BLE001 — writer 失败允许降级
        return ExportEntry(
            kind=ExporterKind.OTIO_FILE, status=ExporterStatus.FAILED,
            tool_version=_OTIO_WRITER_VERSION, errors=[f"OTIO 写入失败：{exc!r}"],
        )


# —— FCPXML：xml.etree 写文件 ——


def _timeline_to_fcpxml_root(timeline: CreativeTimeline) -> ET.Element:
    """CreativeTimeline → FCPXML 1.10 结构（DaVinci/Premiere 可导入的最简子集）。"""
    fcpxml = ET.Element("fcpxml", {"version": "1.10"})
    resources = ET.SubElement(fcpxml, "resources")
    # 一个通用 format 引用（1080x1920 @ rate fps 简化）；真实 exporter 应按 timeline 派生
    ET.SubElement(resources, "format", {
        "id": "r1", "name": f"FFVideoFormat{timeline.rate}",
        "frameDuration": f"1/{timeline.rate}s", "width": "1080", "height": "1920",
    })
    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", {"name": timeline.id})
    project = ET.SubElement(event, "project", {"name": timeline.id})
    seq = ET.SubElement(project, "sequence", {
        "format": "r1",
        "duration": f"{timeline.duration.value}/{timeline.duration.rate}s",
        "tcStart": "0s",
    })
    spine = ET.SubElement(seq, "spine")
    for track in timeline.tracks:
        for seg in track.segments:
            offset = f"{seg.time_range.start.value}/{seg.time_range.start.rate}s"
            dur = f"{seg.time_range.duration.value}/{seg.time_range.duration.rate}s"
            clip = ET.SubElement(spine, "clip", {
                "name": seg.id, "offset": offset, "duration": dur,
            })
            # 扩展字段落 note（DaVinci 会保留 note 供 round-trip）——**全九字段**，含
            # effects / crop_path / localization（VF-306 traceability 链完整不丢）
            effects_payload = [
                {"kind": e.kind, "params": dict(e.params)} for e in seg.effects
            ] if seg.effects else None
            localization_payload = (
                {"language": seg.localization.language, "strategy": seg.localization.strategy}
                if seg.localization is not None else None
            )
            meta = ET.SubElement(clip, "note")
            meta.text = json.dumps({
                "track_kind": track.kind.value,
                "source_ref": seg.source_ref,
                "semantic_role": seg.semantic_role,
                "script_sentence_id": seg.script_sentence_id,
                "speaker_id": seg.speaker_id,
                "provenance_ref": seg.provenance_ref,
                "template_slot": seg.template_slot,
                "effects": effects_payload,
                "crop_path": seg.crop_path,
                "localization": localization_payload,
            }, ensure_ascii=False)
    return fcpxml


def write_fcpxml_file(
    timeline: CreativeTimeline, output_path: str, *, allowed_roots: tuple[str, ...],
) -> ExportEntry:
    """CreativeTimeline → FCPXML 文件。DaVinci/Premiere 可导入的最简子集。"""
    try:
        target = _guard_output_path(output_path, allowed_roots)
        target.parent.mkdir(parents=True, exist_ok=True)
        root = _timeline_to_fcpxml_root(timeline)
        # 用 stdlib 无声明前缀写；FCPXML 消费者容错空白
        text = ET.tostring(root, encoding="unicode")
        preamble = '<?xml version="1.0" encoding="UTF-8"?>\n'
        payload = preamble + text
        target.write_text(payload, encoding="utf-8")
        return ExportEntry(
            kind=ExporterKind.FCPXML, status=ExporterStatus.OK,
            output_path=str(target), tool_version=_FCPXML_WRITER_VERSION,
            bytes_written=len(payload.encode("utf-8")),
        )
    except UnsafeInputPath:
        raise
    except Exception as exc:  # noqa: BLE001
        return ExportEntry(
            kind=ExporterKind.FCPXML, status=ExporterStatus.FAILED,
            tool_version=_FCPXML_WRITER_VERSION, errors=[f"FCPXML 写入失败：{exc!r}"],
        )


# —— JianYing / CapCut：experimental fallback 到"包+README 说明" ——


def _write_experimental_package(
    timeline: CreativeTimeline, output_path: str, allowed_roots: tuple[str, ...],
    kind: ExporterKind, tool_version: str, target_editor: str,
) -> ExportEntry:
    """两家 Adapter 共用：产出目录包 + timeline.json + README（人工导入说明）。§10 底线。"""
    try:
        target_dir = _guard_output_path(output_path, allowed_roots)
        target_dir.mkdir(parents=True, exist_ok=True)
        # 保底：把 CreativeTimeline 用 json 备份到包内（人工/未来 Adapter 可读）
        timeline_json = target_dir / "timeline.json"
        payload = json.dumps(json.loads(timeline.model_dump_json()),
                              ensure_ascii=False, indent=2, sort_keys=True)
        timeline_json.write_text(payload, encoding="utf-8")
        readme = target_dir / "README.md"
        readme_text = (
            f"# VideoForge → {target_editor} 手动导入包\n\n"
            f"本目录由 {tool_version} 生成。{target_editor} 新版本 Draft 采用加密/私有格式；"
            f"VideoForge 暂无稳定 Adapter。请按下述步骤在 {target_editor} 中重建时间线：\n\n"
            f"1. 打开 `timeline.json` 查看 tracks + segments；\n"
            f"2. 在 {target_editor} 中按 `rate={timeline.rate}` 建工程；\n"
            f"3. 依次导入源素材（`source_ref` 字段），按 `time_range` 排列；\n"
            f"4. 复制字幕轨（V4）内容作参考。\n\n"
            f"发布链路已产出 MP4 最终成品；本包仅供后期二次编辑用（§10 底线：导出失败不阻断发布）。"
        )
        readme.write_text(readme_text, encoding="utf-8")
        total_bytes = len(payload.encode("utf-8")) + len(readme_text.encode("utf-8"))
        return ExportEntry(
            kind=kind, status=ExporterStatus.PARTIAL,
            output_path=str(target_dir), tool_version=tool_version,
            warnings=[
                f"{target_editor} 新版本 Draft 加密/私有；已产出包+README 说明供人工导入",
            ],
            bytes_written=total_bytes,
        )
    except UnsafeInputPath:
        raise
    except Exception as exc:  # noqa: BLE001
        return ExportEntry(
            kind=kind, status=ExporterStatus.FAILED,
            tool_version=tool_version, errors=[f"{target_editor} 包写入失败：{exc!r}"],
        )


def write_jianying_package(
    timeline: CreativeTimeline, output_path: str, *, allowed_roots: tuple[str, ...],
) -> ExportEntry:
    """剪映（JianYing）Adapter，experimental —— fallback 到"包+README 说明"（§10）。"""
    return _write_experimental_package(
        timeline, output_path, allowed_roots,
        ExporterKind.JIANYING, _JIANYING_WRITER_VERSION, "剪映 JianYing",
    )


def write_capcut_package(
    timeline: CreativeTimeline, output_path: str, *, allowed_roots: tuple[str, ...],
) -> ExportEntry:
    """CapCut Adapter，experimental —— fallback 到"包+README 说明"（§10）。"""
    return _write_experimental_package(
        timeline, output_path, allowed_roots,
        ExporterKind.CAPCUT, _CAPCUT_WRITER_VERSION, "CapCut",
    )


# —— 批量：跑多个 exporter，独立降级 ——


def export_all(
    timeline: CreativeTimeline,
    plan: dict[ExporterKind, str],
    *,
    allowed_roots: tuple[str, ...],
    report_id: str,
    created_at: datetime,
) -> ExporterReport:
    """跑多个 exporter，独立降级。§10 底线：单个失败不影响其他 exporter 与 MP4 最终渲染。

    plan = {ExporterKind: output_path}。缺失的 kind 视为不需要导出。
    """
    entries: list[ExportEntry] = []
    for kind, path in plan.items():
        try:
            if kind is ExporterKind.OTIO_FILE:
                entries.append(write_otio_file(timeline, path, allowed_roots=allowed_roots))
            elif kind is ExporterKind.FCPXML:
                entries.append(write_fcpxml_file(timeline, path, allowed_roots=allowed_roots))
            elif kind is ExporterKind.JIANYING:
                entries.append(write_jianying_package(timeline, path, allowed_roots=allowed_roots))
            elif kind is ExporterKind.CAPCUT:
                entries.append(write_capcut_package(timeline, path, allowed_roots=allowed_roots))
            else:
                entries.append(ExportEntry(
                    kind=kind, status=ExporterStatus.UNSUPPORTED,
                    errors=[f"未接入 exporter：{kind.value}"],
                ))
        except UnsafeInputPath as exc:
            # 安全违规：绝不静默，记为 FAILED 让批次仍能继续（其他 exporter 不受影响）
            entries.append(ExportEntry(
                kind=kind, status=ExporterStatus.FAILED,
                errors=[f"output_path 越出白名单：{exc}"],
            ))
    return ExporterReport(
        id=report_id, timeline_id=timeline.id, entries=entries, created_at=created_at,
    )


def read_otio_file(path: str) -> dict[str, Any]:
    """读回已写出的 OTIO 文件，供 opentimelineio 或 VF-306 from_otio_mapping 消费。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


__all__ = [
    "export_all",
    "read_otio_file",
    "write_capcut_package",
    "write_fcpxml_file",
    "write_jianying_package",
    "write_otio_file",
]
