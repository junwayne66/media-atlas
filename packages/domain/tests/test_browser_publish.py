"""VF-505 浏览器发布安全 domain 测试：§6 白名单（host 锚定）+ 挑战暂停 + 选择器 + Canary。"""

from videoforge_domain import (
    BrowserChallengeKind,
    SelectorStrategy,
    canary_ok,
    classify_browser_challenge,
    is_blocking_challenge,
    is_domain_allowed,
    preferred_selector,
    should_disable_connector,
)

_WL = ["tiktok.com", "douyin.com"]


# --- §6 域名白名单（host 锚定，防绕过）----------------------------------

def test_whitelisted_hosts_allowed():
    for url in ("https://www.tiktok.com/upload", "https://tiktok.com/x",
                "https://m.douyin.com/x", "http://user:pw@www.tiktok.com:443/x"):
        assert is_domain_allowed(url, _WL), url


def test_path_injection_blocked():
    # evil.com/tiktok.com/x —— host 是 evil.com，路径里的白名单串不算
    assert not is_domain_allowed("https://evil.com/tiktok.com/upload", _WL)


def test_suffix_spoof_blocked():
    # tiktok.com.evil.com —— 后缀是 evil.com，非子域
    assert not is_domain_allowed("https://tiktok.com.evil.com/x", _WL)


def test_prefix_spoof_blocked():
    # faketiktok.com 不是 tiktok.com 也不是其子域
    assert not is_domain_allowed("https://faketiktok.com/x", _WL)


def test_non_whitelisted_blocked():
    assert not is_domain_allowed("https://youtube.com/x", _WL)


def test_backslash_whatwg_bypass_blocked():
    # verifier REFUTED：WHATWG（浏览器/Playwright）把 \ 当 / → 真实 host 是 evil.com
    assert not is_domain_allowed("https://evil.com\\.tiktok.com/upload", _WL)
    assert not is_domain_allowed("https://evil.com\\@tiktok.com/x", _WL)


def test_fragment_whatwg_bypass_blocked():
    # evil.com#@tiktok.com —— # 起 fragment，真实 host 是 evil.com
    assert not is_domain_allowed("https://evil.com#@tiktok.com", _WL)


def test_percent_encoded_host_fail_closed():
    # verifier round-2：%00/%2f 等编码字节——WHATWG 抛错、浏览器无法导航；fail-closed 直接拒
    assert not is_domain_allowed("https://evil.com%2f.tiktok.com", _WL)
    assert not is_domain_allowed("https://evil.com%00.tiktok.com", _WL)
    # 前导点/空标签等非法主机名也拒
    assert not is_domain_allowed("https://.tiktok.com/x", _WL)


def test_query_before_userinfo_not_bypass():
    # tiktok.com?x=@evil.com —— ? 起 query，真实 host 是 tiktok.com（允许，非绕过方向）
    assert is_domain_allowed("https://tiktok.com?x=@evil.com", _WL)


def test_tab_stripped_like_whatwg():
    # evil.com\t.tiktok.com（制表符）→ WHATWG 剥离制表符 → evil.com.tiktok.com（真 tiktok 子域）
    assert is_domain_allowed("https://evil.com\t.tiktok.com/x", _WL)


def test_empty_or_bad_url_blocked():
    assert not is_domain_allowed("", _WL)
    assert not is_domain_allowed("not a url", _WL)


def test_empty_whitelist_blocks_everything():
    assert not is_domain_allowed("https://tiktok.com/x", [])


# --- §6/§13 挑战分类（全部阻塞、转人工）--------------------------------

def test_each_challenge_kind_classified():
    cases = {
        BrowserChallengeKind.LOGIN_EXPIRED: "请重新登录，会话过期",
        BrowserChallengeKind.CAPTCHA: "slider captcha 滑块验证码",
        BrowserChallengeKind.DEVICE_CONFIRM: "扫码确认设备",
        BrowserChallengeKind.CONTENT_WARNING: "内容警告：涉嫌违规",
        BrowserChallengeKind.RISK_CONTROL: "风控异常 security check",
    }
    for kind, signal in cases.items():
        got = classify_browser_challenge(signal)
        assert got is kind, signal
        assert is_blocking_challenge(got)  # 一律阻塞 → 人工


def test_normal_page_is_not_a_challenge():
    assert classify_browser_challenge("upload complete, publish button ready") is None
    assert not is_blocking_challenge(None)


def test_case_insensitive_challenge():
    assert classify_browser_challenge("CAPTCHA REQUIRED") is BrowserChallengeKind.CAPTCHA


def test_spaced_login_phrasings_are_caught():
    # verifier 观察：常见登录墙措辞（空格分隔）此前漏判 → 现在应识别为阻塞
    for text in ("Please log in again", "Your session has expired, please log in",
                 "You have been logged out", "Authentication required"):
        got = classify_browser_challenge(text)
        assert got is BrowserChallengeKind.LOGIN_EXPIRED, text
        assert is_blocking_challenge(got)


# --- §6 选择器优先级 -----------------------------------------------------

def test_selector_priority_prefers_role():
    assert preferred_selector([
        SelectorStrategy.CSS, SelectorStrategy.COORDINATE, SelectorStrategy.ROLE,
    ]) is SelectorStrategy.ROLE


def test_selector_coordinate_is_last_resort():
    assert preferred_selector([SelectorStrategy.COORDINATE]) is (
        SelectorStrategy.COORDINATE)


def test_selector_none_when_empty():
    assert preferred_selector([]) is None


def test_selector_order_full():
    order = [SelectorStrategy.ROLE, SelectorStrategy.LABEL, SelectorStrategy.TEST_ID,
             SelectorStrategy.CSS, SelectorStrategy.COORDINATE]
    for i in range(len(order)):
        # 只提供第 i 及之后的 → 应选第 i 个（最高优先）
        assert preferred_selector(order[i:]) is order[i]


# --- §6 Canary（页面结构契约）------------------------------------------

def test_canary_ok_when_required_present():
    assert canary_ok(["a", "b", "c"], ["a", "b"])
    assert not should_disable_connector(canary_ok(["a", "b", "c"], ["a", "b"]))


def test_canary_fails_and_disables_when_required_missing():
    assert not canary_ok(["a"], ["a", "b"])
    assert should_disable_connector(canary_ok(["a"], ["a", "b"]))


def test_canary_ok_with_no_requirements():
    assert canary_ok([], [])
