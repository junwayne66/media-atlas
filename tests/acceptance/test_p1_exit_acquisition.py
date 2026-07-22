"""P1 Exit 验收（获取）：50+ 试点链接每条都有明确处置，零静默失败。

53 §P1 Exit：「50 个试点链接可导入或明确提示人工回退」。实时下载是停止条件（默认
Unconfigured），故此处验证的是「可导入 或 明确人工回退」这一 OR 条件——每条链接都落入
一个明确、可诊断的处置，绝不静默失败/静默空。
"""

from pathlib import Path

import pytest
from pilot_links import (
    MANUAL,
    NEEDS_EXPANSION,
    RESOLVED_MANUAL_FALLBACK,
    UNRESOLVABLE,
    PilotLink,
    pilot_links,
)

from videoforge_connector_f2 import F2DownloadConnector
from videoforge_connector_yt_dlp import YtDlpDownloadConnector
from videoforge_provider_sdk import (
    DownloadRequest,
    DownloadRouter,
    DownloadStatus,
    UnresolvableUrl,
    resolve_local_file,
    resolve_url,
)

# 可接受的处置（都属「可导入 或 明确人工回退」）；唯一不可接受的是 silent_fail
_ACCEPTABLE = {
    "downloaded",  # 实时下载成功（本 P1 阶段未配置，留作未来）
    "human",  # CHALLENGE/AUTH → 转人工（明确待办）
    RESOLVED_MANUAL_FALLBACK,  # 可识别但实时未配置 → 明确回退手工导入
    NEEDS_EXPANSION,  # 短链 → 明确下一步（展开或手工）
    MANUAL,  # 本地文件 → 手工导入始终可用
    UNRESOLVABLE,  # 不支持 → 明确报错，引导手工导入
}


def _router() -> DownloadRouter:
    # 默认 Unconfigured 连接器：不触网，规范链接必回退手工导入
    return DownloadRouter(
        {
            "download.f2": F2DownloadConnector(),
            "download.yt_dlp": YtDlpDownloadConnector(),
        }
    )


def _disposition(link: PilotLink, router: DownloadRouter, dest: Path) -> str:
    if link.kind == "local":
        rs = resolve_local_file(link.raw)
        return MANUAL if rs.platform == "manual" else "silent_fail"
    try:
        rs = resolve_url(link.raw)
    except UnresolvableUrl:
        return UNRESOLVABLE  # 明确报错（可诊断），非静默
    if rs.needs_expansion:
        return NEEDS_EXPANSION
    route = router.download(DownloadRequest(source=rs, dest_dir=dest))
    if route.ok:
        return "downloaded"
    if route.result.status in (DownloadStatus.CHALLENGE, DownloadStatus.AUTH_REQUIRED):
        return "human"
    if route.manual_fallback:
        return RESOLVED_MANUAL_FALLBACK
    return "silent_fail"  # 不该发生：既没下载、没转人工、也没明确回退


def _all_dispositions(tmp_path: Path) -> dict[str, str]:
    router = _router()
    return {link.raw: _disposition(link, router, tmp_path) for link in pilot_links()}


def test_pilot_set_has_at_least_50_links() -> None:
    assert len(pilot_links()) >= 50


def test_zero_silent_failures(tmp_path) -> None:
    dispositions = _all_dispositions(tmp_path)
    silent = [raw for raw, d in dispositions.items() if d == "silent_fail"]
    assert silent == [], f"存在静默失败链接：{silent}"


def test_hundred_percent_importable_or_manual_fallback(tmp_path) -> None:
    dispositions = _all_dispositions(tmp_path)
    unacceptable = {raw: d for raw, d in dispositions.items() if d not in _ACCEPTABLE}
    assert unacceptable == {}, f"存在非明确处置：{unacceptable}"
    rate = sum(1 for d in dispositions.values() if d in _ACCEPTABLE) / len(dispositions)
    assert rate == 1.0


def test_each_link_matches_expected_disposition(tmp_path) -> None:
    router = _router()
    for link in pilot_links():
        got = _disposition(link, router, tmp_path)
        assert got == link.expected, f"{link.raw!r}: 期望 {link.expected}，实得 {got}"


@pytest.mark.parametrize(
    "category", [RESOLVED_MANUAL_FALLBACK, NEEDS_EXPANSION, MANUAL, UNRESOLVABLE]
)
def test_every_category_is_represented(category, tmp_path) -> None:
    # 试点集覆盖全部处置分支（而非只测一种形态）
    dispositions = set(_all_dispositions(tmp_path).values())
    assert category in dispositions
