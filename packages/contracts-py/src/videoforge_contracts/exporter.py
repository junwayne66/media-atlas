"""NLE 导出合同（docs/modules/42 §10）。

OTIO 主交换格式；DaVinci 优先 OTIO/FCPXML；剪映/CapCut 走 Draft Adapter（experimental，新版本
加密时降级为"包+说明"，不阻断 MP4 最终渲染）。ExporterReport 记录每次导出的结果供审计与
"哪些格式成功、哪些需人工"的调度使用。

安全一致性：output_path 层拒 shell 元字符，与 VF-307/VF-308 一致（纵深防御，即便 exporter
本身不启子进程）。
"""

from datetime import datetime

from pydantic import Field, field_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import ExporterKind, ExporterStatus

_SHELL_META_CHARS = frozenset(";|&<>`$\\\"'\n\r\t")


def _reject_shell_metachars(value: str, field: str) -> str:
    if any(c in _SHELL_META_CHARS for c in value):
        offenders = sorted({c for c in value if c in _SHELL_META_CHARS})
        raise ValueError(f"{field} 含不允许的 shell 元字符 {offenders!r}")
    return value


class ExportEntry(ContractModel):
    """单个 Exporter 的输出结果（一份 timeline 可能同时导出到多种 NLE 格式）。"""

    kind: ExporterKind
    status: ExporterStatus
    output_path: str | None = Field(
        default=None, description="成功时为绝对路径；FAILED/UNSUPPORTED 时为 null"
    )
    tool_version: str | None = Field(default=None, description="导出器版本，供复现")
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    bytes_written: int | None = Field(default=None, ge=0)

    @field_validator("output_path")
    @classmethod
    def _output_path_safe(cls, v: str | None) -> str | None:
        if v is not None:
            _reject_shell_metachars(v, "output_path")
        return v


class ExporterReport(ContractModel):
    """一次导出批次的报告：多 exporter 各自结果 + 时间戳。"""

    id: str = Field(min_length=1)
    timeline_id: str = Field(min_length=1)
    entries: list[ExportEntry] = Field(default_factory=list)
    created_at: datetime
