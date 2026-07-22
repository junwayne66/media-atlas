"""f2 下载连接器：实现 provider-sdk DownloadConnector 端口（docs/modules/41 §2/§3）。

抖音优先、TikTok 兜底——优先级/回退由 provider-sdk DownloadRouter 编排，本连接器只负责
「用 f2 下一条」。与 yt-dlp 连接器共享 provider-sdk 的凭据端口、错误映射与下载辅助
（scrub_metadata / sha256_file / locate_downloaded_media），安全关键逻辑单实现。

- build_argv：纯构造，注入安全——可控值用 `--opt=value` 单 token，无位置参数 URL，绝不拼 shell。
- 验证码/风控 → CHALLENGE（转人工，不绕过）；raw_metadata 已脱敏；产物约束在 dest_dir。
- 默认 runner=Unconfigured、cookie_resolver=Unconfigured：不触网、不静默失败。

注：f2 自动选最佳清晰度，不吃 format_selector；manifest 仍如实记录请求的 format
（作请求身份/Cache Key 一部分）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoforge_connector_f2.runner import PINNED_VERSION, F2Runner, UnconfiguredF2Runner
from videoforge_contracts import ProviderDescriptor
from videoforge_provider_sdk import (
    AcquisitionError,
    AcquisitionErrorCode,
    AcquisitionManifest,
    CookieResolver,
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
    UnconfiguredCookieResolver,
    acquisition_input_digest,
    load_descriptor,
    locate_downloaded_media,
    map_download_error,
    scrub_metadata,
    sha256_file,
    status_for_download_error,
)

CONNECTOR_NAME = "download.f2"
_TOOL = "f2"
_DOWNLOAD_TIMEOUT_S = 1800
_PROBE_TIMEOUT_S = 120

# f2 平台子命令。仅抖音/TikTok（descriptor.platforms）；其余平台不受支持
_SUBCOMMAND = {"douyin": "dy", "tiktok": "tk"}


def load_f2_descriptor() -> ProviderDescriptor:
    # connector.py → videoforge_connector_f2 → src → f2（含 descriptor.yaml）
    return load_descriptor(Path(__file__).resolve().parents[2] / "descriptor.yaml")


class F2DownloadConnector:
    def __init__(
        self,
        descriptor: ProviderDescriptor | None = None,
        *,
        runner: F2Runner | None = None,
        cookie_resolver: CookieResolver | None = None,
    ) -> None:
        self.descriptor = descriptor or load_f2_descriptor()
        self._runner: F2Runner = runner or UnconfiguredF2Runner()
        self._cookies: CookieResolver = cookie_resolver or UnconfiguredCookieResolver()

    # —— 纯构造（可独立测试注入安全）——
    def build_argv(
        self,
        request: DownloadRequest,
        *,
        cookie_file: Path | None = None,
        skip_download: bool = False,
    ) -> list[str]:
        src = request.source
        if src.needs_expansion or not src.canonical_url:
            raise AcquisitionError(
                AcquisitionErrorCode.SOURCE_UNAVAILABLE, "源未解析/短链未展开，无法下载"
            )
        if src.platform == "manual":
            raise AcquisitionError(
                AcquisitionErrorCode.SOURCE_UNAVAILABLE, "手工导入无需下载（本地已有原片）"
            )
        sub = _SUBCOMMAND.get(src.platform)
        if sub is None:
            raise AcquisitionError(
                AcquisitionErrorCode.SOURCE_UNAVAILABLE, f"f2 不支持平台 {src.platform!r}"
            )
        # 可控值一律 --opt=value 单 token（值即便以 - 开头也不会被当新选项）；无位置参数 URL
        argv = [
            sub,  # dy / tk（固定字典，非用户输入）
            f"--url={src.canonical_url}",
            "--mode=one",  # 单个作品
            f"--path={request.dest_dir}",
            "--folderize=false",
            "--json",  # 输出 info JSON 到 stdout
        ]
        if cookie_file is not None:
            argv.append(f"--cookie-file={cookie_file}")
        if skip_download:
            argv.append("--no-download")  # 仅取元数据
        return argv

    def _resolve_cookies(self, request: DownloadRequest) -> Path | None:
        if request.credential_handle is None:
            return None  # 匿名
        return self._cookies.resolve(request.credential_handle).cookie_file

    def _error_result(self, err: AcquisitionError) -> DownloadResult:
        return DownloadResult(
            status=status_for_download_error(err.code),
            connector=CONNECTOR_NAME,
            error_code=err.code,
            detail=err.detail or str(err),
        )

    def _run(self, request: DownloadRequest, *, skip_download: bool, timeout_s: int):
        cookie_file = self._resolve_cookies(request)
        argv = self.build_argv(request, cookie_file=cookie_file, skip_download=skip_download)
        return self._runner.run(argv, timeout_s=timeout_s)

    def download(self, request: DownloadRequest) -> DownloadResult:
        try:
            run = self._run(request, skip_download=False, timeout_s=_DOWNLOAD_TIMEOUT_S)
        except AcquisitionError as err:  # 未解析源 / 未配置 runner / 无法解析句柄
            return self._error_result(err)
        except Exception as exc:  # 子进程超时/OSError 等
            return self._error_result(map_download_error(exc=exc))

        if run.returncode != 0:
            return self._error_result(
                map_download_error(returncode=run.returncode, stderr=run.stderr)
            )
        try:
            info = json.loads(run.stdout)
        except json.JSONDecodeError as exc:
            return self._error_result(
                AcquisitionError(AcquisitionErrorCode.CONNECTOR_SCHEMA_CHANGED, str(exc))
            )

        media_path = locate_downloaded_media(request.dest_dir, info)
        if media_path is None:
            return self._error_result(
                AcquisitionError(AcquisitionErrorCode.DOWNLOAD_INCOMPLETE, "下载完成但产物文件缺失")
            )

        output_sha256, output_size = sha256_file(media_path)
        manifest = AcquisitionManifest(
            source=request.source,
            provider=CONNECTOR_NAME,
            tool=_TOOL,
            tool_version=self._runner.version,
            format_selector=request.format_selector,
            input_digest=acquisition_input_digest(request.source, request.format_selector),
            output_sha256=output_sha256,
            output_size=output_size,
            container=info.get("ext"),
            duration_s=_as_float(info.get("duration")),
            resume_enabled=request.resume,
            fetched_at=datetime.now(UTC),
        )
        return DownloadResult(
            status=DownloadStatus.OK,
            connector=CONNECTOR_NAME,
            manifest=manifest,
            media_path=media_path,
            raw_metadata=scrub_metadata(info),
        )

    def probe(self, request: DownloadRequest) -> DownloadResult:
        """仅取元数据（不下载媒体）。"""
        try:
            run = self._run(request, skip_download=True, timeout_s=_PROBE_TIMEOUT_S)
        except AcquisitionError as err:
            return self._error_result(err)
        except Exception as exc:
            return self._error_result(map_download_error(exc=exc))
        if run.returncode != 0:
            return self._error_result(
                map_download_error(returncode=run.returncode, stderr=run.stderr)
            )
        try:
            info = json.loads(run.stdout)
        except json.JSONDecodeError as exc:
            return self._error_result(
                AcquisitionError(AcquisitionErrorCode.CONNECTOR_SCHEMA_CHANGED, str(exc))
            )
        return DownloadResult(
            status=DownloadStatus.OK, connector=CONNECTOR_NAME, raw_metadata=scrub_metadata(info)
        )

    def health_check(self) -> DownloadResult:
        if self._runner.version in ("unconfigured", ""):
            return DownloadResult(
                status=DownloadStatus.UNCONFIGURED,
                connector=CONNECTOR_NAME,
                error_code=AcquisitionErrorCode.UNCONFIGURED,
                detail=f"实时下载未启用（锁定版本 {PINNED_VERSION}）",
            )
        return DownloadResult(status=DownloadStatus.OK, connector=CONNECTOR_NAME)


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
