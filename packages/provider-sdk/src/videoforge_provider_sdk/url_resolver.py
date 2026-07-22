"""URL 解析：链接/分享文本 → (平台, 内容 ID)（docs/modules/41 §3 ResolveSource）。

纯解析，不触网。短链（v.douyin.com / vm.tiktok.com …）只能标记 needs_expansion，
真正展开（HTTP 重定向）交给可打桩的 ShortLinkExpander——实时展开需网络，默认未启用
（53 §10 停止条件），此前请粘贴规范链接或用手工导入（resolve_local_file，始终可用）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from videoforge_provider_sdk.acquisition import AcquisitionErrorCode, ResolvedSource
from videoforge_provider_sdk.download_errors import AcquisitionError


class UnresolvableUrl(ValueError):
    """无法从输入识别出平台/内容 ID（应引导用户改用规范链接或手工导入）。"""


# 从分享文本里抠出 URL（抖音分享文案含表情/中文标点，需在这些处截断）
_URL_RE = re.compile(r"https?://[^\s'\"，。；、）)】\]<>]+", re.IGNORECASE)

# 短链 host → 平台。只知最终 id 需展开（HEAD 重定向）
_SHORT_HOSTS: dict[str, str] = {
    "v.douyin.com": "douyin",
    "vm.tiktok.com": "tiktok",
    "vt.tiktok.com": "tiktok",
    "t.tiktok.com": "tiktok",
}

# host 后缀 → 平台。平台由 host 决定（而非 URL 里出现的域名子串），否则
# https://evil.com/douyin.com/video/123 会被串味识别成 douyin。
_HOST_SUFFIX_PLATFORM: tuple[tuple[str, str], ...] = (
    ("douyin.com", "douyin"),
    ("tiktok.com", "tiktok"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
)


def _platform_for_host(host: str) -> str | None:
    for base, platform in _HOST_SUFFIX_PLATFORM:
        if host == base or host.endswith("." + base):
            return platform
    return None


_DIGITS = r"(\d{6,25})"
# 规范 URL：(平台, 在已确认 host 的 URL 上匹配 content_id 的正则)
_CANONICAL: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("douyin", re.compile(r"douyin\.com/video/" + _DIGITS, re.IGNORECASE)),
    ("douyin", re.compile(r"douyin\.com/(?:share/)?(?:video|note)/" + _DIGITS, re.IGNORECASE)),
    ("douyin", re.compile(r"douyin\.com/.*?[?&]modal_id=" + _DIGITS, re.IGNORECASE)),
    ("tiktok", re.compile(r"tiktok\.com/(@[\w.\-]+/video/" + _DIGITS + r")", re.IGNORECASE)),
    ("tiktok", re.compile(r"tiktok\.com/.*?[?&]item_id=" + _DIGITS, re.IGNORECASE)),
    (
        "youtube",
        re.compile(
            r"(?:youtube\.com/(?:watch\?[^#]*?\bv=|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})",
            re.IGNORECASE,
        ),
    ),
)


def extract_url_from_text(text: str) -> str | None:
    """从任意文本（含分享文案）抽取首个 URL；无则 None。"""
    m = _URL_RE.search(text)
    if not m:
        return None
    return m.group(0).rstrip(".,;、。")


def _canonicalize(platform: str, content_id: str, tiktok_path: str | None, url: str) -> str:
    if platform == "douyin":
        return f"https://www.douyin.com/video/{content_id}"
    if platform == "youtube":
        return f"https://www.youtube.com/watch?v={content_id}"
    if platform == "tiktok":
        if tiktok_path:  # @user/video/<id>：yt-dlp 可直接下载
            return f"https://www.tiktok.com/{tiktok_path}"
        return f"https://www.tiktok.com/video/{content_id}"
    return url


def resolve_url(raw: str) -> ResolvedSource:
    """链接/分享文本 → ResolvedSource。短链返回 needs_expansion；无法识别抛 UnresolvableUrl。"""
    raw = raw.strip()
    if not raw:
        raise UnresolvableUrl("空输入")
    url = raw if re.match(r"^https?://", raw, re.IGNORECASE) else extract_url_from_text(raw)
    if url is None:
        raise UnresolvableUrl(f"输入里没有可识别的链接：{raw[:80]!r}（本地文件请走手工导入）")

    host = urlparse(url).netloc.lower().split(":")[0]
    platform = _platform_for_host(host)
    if platform is None:
        raise UnresolvableUrl(f"非支持平台域名：{host}（本地文件请走手工导入）")

    if host in _SHORT_HOSTS:  # 短链：id 未知，须先展开
        return ResolvedSource(
            platform=platform,
            content_id="",
            canonical_url="",
            raw_input=raw,
            needs_expansion=True,
            short_url=url,
        )

    for p, rx in _CANONICAL:
        if p != platform:  # host 锚定：只用该平台的抽取规则，路径里的别家域名不串味
            continue
        m = rx.search(url)
        if not m:
            continue
        if platform == "tiktok" and m.re.groups == 2:
            tiktok_path, content_id = m.group(1), m.group(2)
        else:
            tiktok_path, content_id = None, m.group(m.re.groups)
        return ResolvedSource(
            platform=platform,
            content_id=content_id,
            canonical_url=_canonicalize(platform, content_id, tiktok_path, url),
            raw_input=raw,
            needs_expansion=False,
        )
    raise UnresolvableUrl(f"识别到平台 {platform} 但无法提取内容 ID：{url}")


def resolve_local_file(path: str | Path) -> ResolvedSource:
    """手工导入：本地原片 → platform=manual（始终可用的回退，README §4/41 §2）。"""
    p = Path(path)
    if not p.name:
        raise UnresolvableUrl(f"非法本地路径：{path!r}")
    return ResolvedSource(
        platform="manual",
        content_id=p.name,
        canonical_url=str(p),
        raw_input=str(path),
        needs_expansion=False,
    )


class ShortLinkExpander(Protocol):
    def expand(self, short_url: str) -> str:
        """展开短链为可解析的规范 URL；失败抛 AcquisitionError。"""
        ...


class FixtureShortLinkExpander:
    """测试/离线：按录制映射展开短链，全程不触网。"""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = dict(mapping)

    def expand(self, short_url: str) -> str:
        if short_url not in self._mapping:
            raise AcquisitionError(
                AcquisitionErrorCode.SOURCE_UNAVAILABLE, f"短链无录制映射：{short_url}"
            )
        return self._mapping[short_url]


class UnconfiguredShortLinkExpander:
    """实时短链展开未启用（需网络）——返回停止条件，不静默失败。"""

    def expand(self, short_url: str) -> str:
        raise AcquisitionError(
            AcquisitionErrorCode.UNCONFIGURED,
            "短链展开需实时网络，未启用；请粘贴规范链接或用手工导入",
        )


def resolve(raw: str, expander: ShortLinkExpander | None = None) -> ResolvedSource:
    """解析并（在提供 expander 时）展开短链。无 expander 且是短链则原样返回 needs_expansion。"""
    resolved = resolve_url(raw)
    if not resolved.needs_expansion:
        return resolved
    if expander is None:
        return resolved
    expanded = expander.expand(resolved.short_url or raw)
    out = resolve_url(expanded)
    # 保留最初的原始输入作为 provenance
    return ResolvedSource(
        platform=out.platform,
        content_id=out.content_id,
        canonical_url=out.canonical_url,
        raw_input=resolved.raw_input,
        needs_expansion=out.needs_expansion,
        short_url=resolved.short_url,
    )
