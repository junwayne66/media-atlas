"""yt-dlp 下载连接器：实现 provider-sdk DownloadConnector 端口（docs/modules/41 §3）。

- build_argv：纯构造，注入安全——所有调用方可控值用 `--opt=value` 单 token 形式，
  URL 前置 `--` 停止选项解析，绝不拼 shell 字符串。
- download：解析 Cookie handle（不透明）→ 跑 runner → returncode/stderr 映射 §12 →
  解析 info-dict → 定位产物 → 流式 sha256 → 组可重放 AcquisitionManifest。
- 验证码/风控 → CHALLENGE（转人工，不绕过）；返回的 raw_metadata 已脱敏（无 Cookie/Token）。
- 默认 runner=Unconfigured、cookie_resolver=Unconfigured：不触网、不静默失败。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videoforge_connector_yt_dlp.cookies import CookieResolver, UnconfiguredCookieResolver
from videoforge_connector_yt_dlp.runner import (
    PINNED_VERSION,
    UnconfiguredYtDlpRunner,
    YtDlpRunner,
)
from videoforge_contracts import ProviderDescriptor
from videoforge_provider_sdk import (
    AcquisitionError,
    AcquisitionErrorCode,
    AcquisitionManifest,
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
    acquisition_input_digest,
    load_descriptor,
    map_ytdlp_error,
    status_for_download_error,
)

CONNECTOR_NAME = "download.yt_dlp"
_TOOL = "yt-dlp"
_DOWNLOAD_TIMEOUT_S = 1800
_PROBE_TIMEOUT_S = 120

# 返回给上层的 raw_metadata 里必须抹掉的机密键（子串匹配，递归）
_SENSITIVE_KEY_MARKERS = (
    "cookie",
    "authorization",
    "token",
    "password",
    "credential",
    "http_headers",
)


def load_yt_dlp_descriptor() -> ProviderDescriptor:
    # connector.py → videoforge_connector_yt_dlp → src → yt-dlp（含 descriptor.yaml）
    return load_descriptor(Path(__file__).resolve().parents[2] / "descriptor.yaml")


def _scrub(obj: Any) -> Any:
    """递归剔除机密键——info-dict 常含 http_headers.Cookie / 各格式的鉴权头。"""
    if isinstance(obj, dict):
        return {
            k: _scrub(v)
            for k, v in obj.items()
            if not any(m in str(k).lower() for m in _SENSITIVE_KEY_MARKERS)
        }
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


class YtDlpDownloadConnector:
    def __init__(
        self,
        descriptor: ProviderDescriptor | None = None,
        *,
        runner: YtDlpRunner | None = None,
        cookie_resolver: CookieResolver | None = None,
    ) -> None:
        self.descriptor = descriptor or load_yt_dlp_descriptor()
        self._runner: YtDlpRunner = runner or UnconfiguredYtDlpRunner()
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
        # 所有可控值用 --opt=value 单 token：即便 value 以 - 开头也不会被当新选项
        argv = [
            "--no-playlist",  # 只下单条，不误抓整播放列表
            "--no-progress",
            "--no-overwrites",  # 幂等：已存在完成文件不重下
            f"--format={request.format_selector}",
            "--dump-single-json",  # 输出 info-dict JSON 到 stdout
        ]
        argv.append("--continue" if request.resume else "--no-continue")  # 断点续传
        if cookie_file is not None:
            argv.append(f"--cookies={cookie_file}")
        if request.max_filesize_mb is not None:
            argv.append(f"--max-filesize={request.max_filesize_mb}M")
        if skip_download:
            argv.append("--skip-download")
        else:
            argv.append("--no-simulate")  # --dump-single-json 默认 simulate，下载路径须关掉
            argv.append(f"--paths=home:{request.dest_dir}")
            argv.append("--output=%(id)s.%(ext)s")
        argv.append("--")  # 停止选项解析——其后一律当位置参数（URL）
        argv.append(src.canonical_url)
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

    def download(self, request: DownloadRequest) -> DownloadResult:
        try:
            cookie_file = self._resolve_cookies(request)
            argv = self.build_argv(request, cookie_file=cookie_file)
        except AcquisitionError as err:
            return self._error_result(err)

        try:
            run = self._runner.run(argv, timeout_s=_DOWNLOAD_TIMEOUT_S)
        except AcquisitionError as err:  # UnconfiguredYtDlpRunner 抛 UNCONFIGURED
            return self._error_result(err)
        except Exception as exc:  # 子进程超时/OSError 等
            return self._error_result(map_ytdlp_error(exc=exc))

        if run.returncode != 0:
            return self._error_result(
                map_ytdlp_error(returncode=run.returncode, stderr=run.stderr)
            )

        try:
            info = json.loads(run.stdout)
        except json.JSONDecodeError as exc:
            # 输出不是预期 info-dict：提取路径假设失效 → 熔断信号
            return self._error_result(
                AcquisitionError(AcquisitionErrorCode.CONNECTOR_SCHEMA_CHANGED, str(exc))
            )

        media_path = self._locate_media(request, info)
        if media_path is None:
            return self._error_result(
                AcquisitionError(AcquisitionErrorCode.DOWNLOAD_INCOMPLETE, "下载完成但产物文件缺失")
            )

        output_sha256, output_size = _sha256_file(media_path)
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
            raw_metadata=_scrub(info),
        )

    def probe(self, request: DownloadRequest) -> DownloadResult:
        """仅取元数据（不下载媒体）。"""
        try:
            cookie_file = self._resolve_cookies(request)
            argv = self.build_argv(request, cookie_file=cookie_file, skip_download=True)
        except AcquisitionError as err:
            return self._error_result(err)
        try:
            run = self._runner.run(argv, timeout_s=_PROBE_TIMEOUT_S)
        except AcquisitionError as err:
            return self._error_result(err)
        except Exception as exc:
            return self._error_result(map_ytdlp_error(exc=exc))
        if run.returncode != 0:
            return self._error_result(
                map_ytdlp_error(returncode=run.returncode, stderr=run.stderr)
            )
        try:
            info = json.loads(run.stdout)
        except json.JSONDecodeError as exc:
            return self._error_result(
                AcquisitionError(AcquisitionErrorCode.CONNECTOR_SCHEMA_CHANGED, str(exc))
            )
        return DownloadResult(
            status=DownloadStatus.OK, connector=CONNECTOR_NAME, raw_metadata=_scrub(info)
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

    def _locate_media(self, request: DownloadRequest, info: dict[str, Any]) -> Path | None:
        candidates: list[str | None] = []
        downloads = info.get("requested_downloads")
        if isinstance(downloads, list) and downloads and isinstance(downloads[0], dict):
            candidates.append(downloads[0].get("filepath"))
        candidates.extend([info.get("filepath"), info.get("_filename")])
        vid, ext = info.get("id"), info.get("ext")
        if vid and ext:
            candidates.append(f"{vid}.{ext}")
        dest = request.dest_dir.resolve()
        for cand in candidates:
            if not cand:
                continue
            p = Path(cand)
            p = p if p.is_absolute() else request.dest_dir / p.name
            # 纵深防御：产物必须落在 dest_dir 内——不信任 info-dict 给的越界绝对路径
            try:
                p.resolve().relative_to(dest)
            except ValueError:
                continue
            if p.is_file():
                return p
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
