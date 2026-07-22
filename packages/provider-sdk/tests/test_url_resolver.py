"""URL 解析：链接/分享文本 → 平台 + 内容 ID；短链标记 needs_expansion；manual 回退。"""

import pytest

from videoforge_provider_sdk.acquisition import AcquisitionErrorCode
from videoforge_provider_sdk.download_errors import AcquisitionError
from videoforge_provider_sdk.url_resolver import (
    FixtureShortLinkExpander,
    UnconfiguredShortLinkExpander,
    UnresolvableUrl,
    extract_url_from_text,
    resolve,
    resolve_local_file,
    resolve_url,
)


def test_douyin_canonical_video_url() -> None:
    r = resolve_url("https://www.douyin.com/video/7412345678901234567")
    assert r.platform == "douyin"
    assert r.content_id == "7412345678901234567"
    assert r.canonical_url == "https://www.douyin.com/video/7412345678901234567"
    assert r.needs_expansion is False


def test_douyin_modal_id_query_form() -> None:
    r = resolve_url("https://www.douyin.com/discover?modal_id=7412345678901234567")
    assert r.platform == "douyin"
    assert r.content_id == "7412345678901234567"


def test_tiktok_canonical_preserves_user_handle() -> None:
    r = resolve_url("https://www.tiktok.com/@some.user/video/7298765432109876543?is_copy_url=1")
    assert r.platform == "tiktok"
    assert r.content_id == "7298765432109876543"
    # 规范 URL 保留 @user（yt-dlp 可直接下载），去掉跟踪 query
    assert r.canonical_url == "https://www.tiktok.com/@some.user/video/7298765432109876543"


def test_youtube_watch_shorts_and_youtu_be() -> None:
    for url, cid in [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ]:
        r = resolve_url(url)
        assert r.platform == "youtube"
        assert r.content_id == cid
        assert r.needs_expansion is False  # youtu.be 直接带 id，无需展开


def test_douyin_short_link_needs_expansion() -> None:
    r = resolve_url("https://v.douyin.com/iRNBho6G/")
    assert r.platform == "douyin"
    assert r.needs_expansion is True
    assert r.content_id == ""  # 未展开前无 id
    assert r.short_url == "https://v.douyin.com/iRNBho6G/"


def test_tiktok_short_hosts_need_expansion() -> None:
    for host in ("vm.tiktok.com", "vt.tiktok.com"):
        r = resolve_url(f"https://{host}/ZMabcdef1/")
        assert r.platform == "tiktok"
        assert r.needs_expansion is True


def test_share_text_extracts_url() -> None:
    text = "7.88 复制打开抖音，看看【AI 拆解】的作品 https://v.douyin.com/iRNBho6G/ 记得关注哦"
    assert extract_url_from_text(text) == "https://v.douyin.com/iRNBho6G/"
    r = resolve_url(text)
    assert r.platform == "douyin"
    assert r.needs_expansion is True


def test_unknown_platform_raises() -> None:
    with pytest.raises(UnresolvableUrl):
        resolve_url("https://example.com/watch/abc")
    with pytest.raises(UnresolvableUrl):
        resolve_url("这里没有链接")


def test_platform_anchored_to_host_not_path_substring() -> None:
    # 平台由 host 决定：路径里出现别家平台域名不得串味识别
    with pytest.raises(UnresolvableUrl):
        resolve_url("https://evil.com/douyin.com/video/7412345678901234567")
    with pytest.raises(UnresolvableUrl):
        resolve_url("https://evil.com/www.tiktok.com/@u/video/7298765432109876543")


def test_manual_local_file_always_available() -> None:
    r = resolve_local_file("/Users/me/Movies/原片.mp4")
    assert r.platform == "manual"
    assert r.content_id == "原片.mp4"
    assert r.canonical_url == "/Users/me/Movies/原片.mp4"
    assert r.needs_expansion is False


def test_fixture_expander_resolves_short_to_canonical() -> None:
    expander = FixtureShortLinkExpander(
        {"https://v.douyin.com/iRNBho6G/": "https://www.douyin.com/video/7412345678901234567"}
    )
    r = resolve("https://v.douyin.com/iRNBho6G/", expander)
    assert r.platform == "douyin"
    assert r.content_id == "7412345678901234567"
    assert r.needs_expansion is False
    # 保留最初原始输入 + 短链 provenance
    assert r.raw_input == "https://v.douyin.com/iRNBho6G/"
    assert r.short_url == "https://v.douyin.com/iRNBho6G/"


def test_resolve_without_expander_keeps_needs_expansion() -> None:
    r = resolve("https://v.douyin.com/iRNBho6G/")  # 无 expander
    assert r.needs_expansion is True


def test_unconfigured_expander_is_stop_condition() -> None:
    with pytest.raises(AcquisitionError) as ei:
        resolve("https://v.douyin.com/iRNBho6G/", UnconfiguredShortLinkExpander())
    assert ei.value.code == AcquisitionErrorCode.UNCONFIGURED


def test_fixture_expander_unmapped_short_link_errors() -> None:
    with pytest.raises(AcquisitionError) as ei:
        FixtureShortLinkExpander({}).expand("https://v.douyin.com/zzz/")
    assert ei.value.code == AcquisitionErrorCode.SOURCE_UNAVAILABLE
