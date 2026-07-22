"""获取（下载）连接器端口（docs/modules/41 §2/§3，docs/implementation/51 §4）。

DownloadProvider 实现本协议，只进出结构化记录，业务模块不依赖任何下载工具的
内部结构（README §4 规则 1）。与发现端口的 ConnectorErrorCode 相互独立：这里是
获取层 §12 错误码。安全立场（53 §10 停止条件、README §4）：

- 实时下载需真实资源/账号——默认不触网；真实 runner 须显式构造真实二进制。
- Cookie 走不透明 credential_handle，绝不在请求/日志/argv 里出现明文 Cookie。
- 验证码/风控 → CHALLENGE，转人工，绝不尝试绕过。
- 每次成功获取产出可重放的 AcquisitionManifest（输入哈希 + 工具版本 + 输出哈希）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from videoforge_contracts import ProviderDescriptor


class DownloadStatus(StrEnum):
    OK = "ok"  # 已获取媒体 + manifest
    FAILED = "failed"  # 获取失败（error_code 说明分类）
    UNCONFIGURED = "unconfigured"  # 实时下载未配置/未授权（停止条件）
    CHALLENGE = "challenge"  # 验证码/风控，转人工（不绕过）
    AUTH_REQUIRED = "auth_required"  # 需登录凭据（Cookie handle），转人工提供


class AcquisitionErrorCode(StrEnum):
    """获取层错误码。前 7 个是 docs/modules/41 §12 的下载相关码，逐字保留；

    后 3 个是运行期分类（未配置/挑战/未知），错误类别决定重试/切 Provider/人工/终止。
    """

    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    CONNECTOR_SCHEMA_CHANGED = "CONNECTOR_SCHEMA_CHANGED"
    DOWNLOAD_INCOMPLETE = "DOWNLOAD_INCOMPLETE"
    MEDIA_CORRUPT = "MEDIA_CORRUPT"
    UNSUPPORTED_CODEC = "UNSUPPORTED_CODEC"
    # —— 运行期分类（非 §12 媒体码）——
    CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
    UNCONFIGURED = "UNCONFIGURED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class ResolvedSource:
    """URL 解析结果：平台 + 平台内容 ID。短链需先展开（needs_expansion）。"""

    platform: str  # douyin / tiktok / youtube / manual；未知为 ""
    content_id: str  # 平台内容 ID；manual 用文件名/本地标识；短链未展开时为 ""
    canonical_url: str  # 规范化 URL；manual 为本地路径；短链未展开时为 ""
    raw_input: str  # 原始输入（分享文本/链接/路径），保留 provenance
    needs_expansion: bool = False  # 短链：须先经 ShortLinkExpander 展开
    short_url: str | None = None  # 短链原文（needs_expansion 时）


@dataclass(frozen=True)
class DownloadRequest:
    source: ResolvedSource
    dest_dir: Path
    format_selector: str = "best"
    credential_handle: str | None = None  # 不透明句柄，绝非明文 Cookie
    resume: bool = True  # 断点续传（.part 复用）
    max_filesize_mb: int | None = None


@dataclass(frozen=True)
class AcquisitionManifest:
    """可重放的获取 Job Manifest（README §4：输入哈希 + 工具版本 + 输出哈希）。

    input_digest 是获取请求身份的稳定哈希，可作 Activity Cache Key 的一部分
    （41 §11）并支持逐位重放。
    """

    source: ResolvedSource
    provider: str  # 连接器名，如 download.yt_dlp
    tool: str  # yt-dlp
    tool_version: str  # 锁定/探测到的版本
    format_selector: str
    input_digest: str  # acquisition_input_digest()
    output_sha256: str  # 输出文件哈希
    output_size: int
    container: str | None  # 容器/扩展名，如 mp4
    duration_s: float | None
    resume_enabled: bool  # 是否启用断点续传（--continue）
    fetched_at: datetime


def acquisition_input_digest(source: ResolvedSource, format_selector: str) -> str:
    """获取请求身份的稳定 sha256。规范 URL + content_id + 格式选择决定输出恒定。"""
    material = "\n".join(
        [source.platform, source.content_id, source.canonical_url, format_selector]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass
class DownloadResult:
    status: DownloadStatus
    connector: str
    manifest: AcquisitionManifest | None = None
    media_path: Path | None = None
    # 原始 info-dict（脱敏后由调用方另存诊断 Artifact，51 §12）；不含明文 Cookie
    raw_metadata: dict[str, Any] | None = field(default=None)
    error_code: AcquisitionErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == DownloadStatus.OK


# CHALLENGE/AUTH/UNCONFIGURED 是独立 DownloadStatus；其余错误码归入 FAILED
_STATUS_BY_CODE: dict[AcquisitionErrorCode, DownloadStatus] = {
    AcquisitionErrorCode.CHALLENGE_REQUIRED: DownloadStatus.CHALLENGE,
    AcquisitionErrorCode.AUTH_REQUIRED: DownloadStatus.AUTH_REQUIRED,
    AcquisitionErrorCode.UNCONFIGURED: DownloadStatus.UNCONFIGURED,
}


def status_for_download_error(code: AcquisitionErrorCode) -> DownloadStatus:
    return _STATUS_BY_CODE.get(code, DownloadStatus.FAILED)


@runtime_checkable
class DownloadConnector(Protocol):
    descriptor: ProviderDescriptor

    def download(self, request: DownloadRequest) -> DownloadResult: ...

    def probe(self, request: DownloadRequest) -> DownloadResult:
        """仅取元数据（不下载媒体），用于格式协商/可用性检查。"""
        ...

    def health_check(self) -> DownloadResult: ...
