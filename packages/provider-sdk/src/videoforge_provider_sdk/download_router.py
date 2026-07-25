"""下载优先级 + 回退编排（docs/modules/41 §2）。

每平台有明确的下载 provider 优先级：抖音 f2 优先、yt-dlp 兜底；TikTok yt-dlp 优先、
f2 兜底；耗尽后回退手工导入（始终可用）。回退语义严守 README §4 不可协商规则：

- OK：成功，终止。
- CHALLENGE / AUTH_REQUIRED：**终止**，转人工。换一个下载器去绕过平台的验证码/登录墙，
  等于绕过风控（违背「验证码/风控 → WAITING_FOR_HUMAN，绝不绕过」），故不回退。
- UNCONFIGURED / 其它 FAILED：回退到下一个 provider（此路未配置/失效，另一路也许可行）。

返回可解释的 attempts 轨迹，便于诊断「为什么走到手工导入」。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from videoforge_provider_sdk.acquisition import (
    AcquisitionErrorCode,
    DownloadConnector,
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
)

# 平台 → 按优先级排序的连接器名（41 §2）
DOWNLOAD_PRIORITY: dict[str, tuple[str, ...]] = {
    "douyin": ("download.f2", "download.yt_dlp"),  # 抖音：f2 优先，yt-dlp 兜底
    "tiktok": ("download.yt_dlp", "download.f2"),  # TikTok：yt-dlp 优先，f2 兜底
    "youtube": ("download.yt_dlp",),
}

# 终止状态：命中则不再回退下一个 provider
_TERMINAL = frozenset({DownloadStatus.OK, DownloadStatus.CHALLENGE, DownloadStatus.AUTH_REQUIRED})


@dataclass(frozen=True)
class DownloadAttempt:
    connector: str
    status: DownloadStatus
    error_code: AcquisitionErrorCode | None


@dataclass
class DownloadRouteResult:
    result: DownloadResult  # 成功结果，或链上最后一次（失败）结果
    attempts: list[DownloadAttempt] = field(default_factory=list)
    manual_fallback: bool = False  # 链耗尽/无可用 provider → 应转手工导入

    @property
    def ok(self) -> bool:
        return self.result.ok


class DownloadRouter:
    def __init__(
        self,
        connectors: dict[str, DownloadConnector],
        *,
        priority: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._connectors = dict(connectors)
        self._priority = priority or DOWNLOAD_PRIORITY

    def chain_for(self, platform: str) -> list[str]:
        """该平台按优先级、且实际已注册的连接器名（可解释/可测）。"""
        return [n for n in self._priority.get(platform, ()) if n in self._connectors]

    def download(self, request: DownloadRequest) -> DownloadRouteResult:
        platform = request.source.platform
        attempts: list[DownloadAttempt] = []
        last: DownloadResult | None = None
        for name in self._priority.get(platform, ()):
            conn = self._connectors.get(name)
            if conn is None:  # 该 provider 未注册，跳过
                continue
            res = conn.download(request)
            attempts.append(DownloadAttempt(name, res.status, res.error_code))
            last = res
            if res.status in _TERMINAL:
                return DownloadRouteResult(res, attempts, manual_fallback=False)
            # 非终止（UNCONFIGURED / 其它 FAILED）→ 回退下一个
        # 链耗尽，或平台无优先级/无已注册 provider → 手工导入兜底
        result = last or DownloadResult(
            status=DownloadStatus.FAILED,
            connector="download.router",
            error_code=AcquisitionErrorCode.UNCONFIGURED,
            detail=f"平台 {platform!r} 无可用下载 provider；请手工导入本地原片",
        )
        return DownloadRouteResult(result, attempts, manual_fallback=True)
