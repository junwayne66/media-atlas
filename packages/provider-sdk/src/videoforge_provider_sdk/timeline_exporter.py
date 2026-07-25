"""时间线交换格式导出端口 + OTIO Fake Exporter（docs/modules/42 §8，§10）。

ADR-003：CreativeTimeline 是领域真值；导出到 OTIO/FCPXML/剪映/CapCut 是外向映射，不是抽取式
provider。本端口把 CreativeTimeline → 交换格式字典（不写文件、不引 opentimelineio 运行时——
真实 .otio 文件写入延后至下游 Exporter 层，opentimelineio 属 Apache-2.0 L0 可直接引入）。

默认 UnconfiguredTimelineExporter 返回 UNCONFIGURED，Fake 返回 domain 的 OTIO dict 映射。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from videoforge_contracts import CreativeTimeline


class TimelineExporterStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"


class TimelineExporterErrorCode(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    INVALID_TIMELINE = "INVALID_TIMELINE"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class TimelineExportRequest:
    timeline: CreativeTimeline
    target_format: str = "otio"


@dataclass
class TimelineExportResult:
    status: TimelineExporterStatus
    provider: str
    format: str
    payload: dict[str, Any] = field(default_factory=dict)
    error_code: TimelineExporterErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == TimelineExporterStatus.OK


@runtime_checkable
class TimelineExporter(Protocol):
    name: str
    format: str
    execution_location: str

    def export(self, request: TimelineExportRequest) -> TimelineExportResult:
        """CreativeTimeline → 目标交换格式（dict/内存表示；写文件由下游 Exporter 具体实现）。"""
        ...

    def health_check(self) -> TimelineExportResult: ...


class UnconfiguredTimelineExporter:
    """默认：真实 Exporter 未接入。返回 UNCONFIGURED，不静默假装。"""

    def __init__(
        self,
        target_format: str = "otio",
        *,
        name: str | None = None,
        execution_location: str = "local",
    ) -> None:
        self.format = target_format
        self.name = name or f"timeline.exporter.{target_format}.unconfigured"
        self.execution_location = execution_location

    def export(self, request: TimelineExportRequest) -> TimelineExportResult:
        return TimelineExportResult(
            status=TimelineExporterStatus.UNCONFIGURED,
            provider=self.name,
            format=self.format,
            error_code=TimelineExporterErrorCode.UNCONFIGURED,
            detail=f"目标交换格式 {self.format} 的 Exporter 未接入（需 pip 包/序列化器）",
        )

    def health_check(self) -> TimelineExportResult:
        return TimelineExportResult(
            status=TimelineExporterStatus.UNCONFIGURED,
            provider=self.name,
            format=self.format,
        )


class OtioDictExporter:
    """OTIO 内存字典 Exporter（不写文件、不引 opentimelineio）。

    映射函数（CreativeTimeline → OTIO dict）由调用方从纯域 domain.to_otio_mapping 注入——
    以此保持 provider-sdk src 层的 contracts-only 分层纯净规则（不 import videoforge_domain）。
    真实 .otio 文件写入由下游 Exporter 层完成（opentimelineio 属 Apache-2.0 L0，可后续接入）。
    """

    def __init__(
        self,
        mapper: Callable[[CreativeTimeline], dict[str, Any]],
        *,
        name: str = "timeline.exporter.otio.dict",
        execution_location: str = "local",
    ) -> None:
        self.format = "otio"
        self.name = name
        self.execution_location = execution_location
        self._mapper = mapper

    def export(self, request: TimelineExportRequest) -> TimelineExportResult:
        payload = self._mapper(request.timeline)
        return TimelineExportResult(
            status=TimelineExporterStatus.OK,
            provider=self.name,
            format=self.format,
            payload=payload,
        )

    def health_check(self) -> TimelineExportResult:
        return TimelineExportResult(
            status=TimelineExporterStatus.OK,
            provider=self.name,
            format=self.format,
        )


__all__ = [
    "OtioDictExporter",
    "TimelineExportRequest",
    "TimelineExportResult",
    "TimelineExporter",
    "TimelineExporterErrorCode",
    "TimelineExporterStatus",
    "UnconfiguredTimelineExporter",
]
