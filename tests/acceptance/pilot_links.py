"""P1 Exit 试点链接集（docs/implementation/54 §1、53 §P1 Exit）。

全部为中性合成样本（NOT 真实抓取的私有 URL）——只验证「解析→路由→处置」在各种形态下
都给出明确处置，绝不静默失败。实时下载是停止条件（默认 Unconfigured），故规范链接的
期望处置是「明确人工回退」，短链是「需展开」，本地文件是「手工导入」，不支持的是「明确报错」。

处置类别（期望）：
- resolved_manual_fallback：可识别平台+内容 ID，但实时下载未配置 → 路由明确回退手工导入。
- needs_expansion：短链，需先展开（粘贴规范链接或手工导入）。
- manual：本地文件，手工导入始终可用。
- unresolvable_clear_error：不支持的域名/非链接 → 明确报错，引导手工导入。
"""

from __future__ import annotations

from dataclasses import dataclass

RESOLVED_MANUAL_FALLBACK = "resolved_manual_fallback"
NEEDS_EXPANSION = "needs_expansion"
MANUAL = "manual"
UNRESOLVABLE = "unresolvable_clear_error"


@dataclass(frozen=True)
class PilotLink:
    raw: str
    kind: str  # "url" | "local"
    expected: str


def _id(n: int) -> str:
    # 合成 19 位平台内容 ID（7 开头，形态逼真但非真实）
    return f"7{n:018d}"[:19]


def pilot_links() -> list[PilotLink]:
    links: list[PilotLink] = []

    # —— 抖音 25：规范 15（video 12 + modal_id 3）+ 短链/分享文本 10 ——
    for i in range(12):
        links.append(
            PilotLink(
                f"https://www.douyin.com/video/{_id(1000 + i)}", "url", RESOLVED_MANUAL_FALLBACK
            )
        )
    for i in range(3):
        links.append(
            PilotLink(
                f"https://www.douyin.com/discover?modal_id={_id(2000 + i)}",
                "url",
                RESOLVED_MANUAL_FALLBACK,
            )
        )
    for i in range(5):
        links.append(PilotLink(f"https://v.douyin.com/iR{i}Ab{i}Cd/", "url", NEEDS_EXPANSION))
    for i in range(5):
        links.append(
            PilotLink(
                f"{i}.88 复制打开抖音看作品 https://v.douyin.com/zZ{i}xY{i}/ 关注",
                "url",
                NEEDS_EXPANSION,
            )
        )

    # —— TikTok 25：规范 15（@user/video 12 + item_id 3）+ 短链/分享文本 10 ——
    for i in range(12):
        links.append(
            PilotLink(
                f"https://www.tiktok.com/@creator{i}/video/{_id(3000 + i)}",
                "url",
                RESOLVED_MANUAL_FALLBACK,
            )
        )
    for i in range(3):
        links.append(
            PilotLink(
                f"https://www.tiktok.com/foryou?item_id={_id(4000 + i)}",
                "url",
                RESOLVED_MANUAL_FALLBACK,
            )
        )
    for i in range(5):
        host = "vm.tiktok.com" if i % 2 == 0 else "vt.tiktok.com"
        links.append(PilotLink(f"https://{host}/ZM{i}abc{i}/", "url", NEEDS_EXPANSION))
    for i in range(5):
        links.append(
            PilotLink(
                f"Check this out https://vm.tiktok.com/ZS{i}xyz{i}/ #ai #tech",
                "url",
                NEEDS_EXPANSION,
            )
        )

    # —— YouTube 4（yt-dlp 支持；实时未配置 → 手工回退）——
    _yt = RESOLVED_MANUAL_FALLBACK
    links.append(PilotLink("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "url", _yt))
    links.append(PilotLink("https://youtu.be/dQw4w9WgXcQ?si=abc", "url", _yt))
    links.append(PilotLink("https://www.youtube.com/shorts/abcDEF12345", "url", _yt))
    links.append(PilotLink("https://m.youtube.com/watch?v=abcDEF12345", "url", _yt))

    # —— 不支持/非链接 4（明确报错，引导手工导入）——
    links.append(PilotLink("https://example.com/watch/abc", "url", UNRESOLVABLE))
    links.append(PilotLink("https://www.bilibili.com/video/BV1xx411c7mD", "url", UNRESOLVABLE))
    links.append(PilotLink("这段文字里根本没有链接", "url", UNRESOLVABLE))
    links.append(
        PilotLink("https://evil.example/douyin.com/video/7123456789012345678", "url", UNRESOLVABLE)
    )

    # —— 本地文件 3（手工导入始终可用）——
    links.append(PilotLink("/Users/pilot/Movies/原片_01.mp4", "local", MANUAL))
    links.append(PilotLink("/Users/pilot/Downloads/clip 02.mov", "local", MANUAL))
    links.append(PilotLink("/tmp/manual/sample-03.mp4", "local", MANUAL))

    return links
