"""浏览器发布 Adapter 安全策略（docs/modules/44 §6）。纯函数。

VF-505 的**安全逻辑**（供 workflow + Fake adapter 共用）：

- `is_domain_allowed(url, whitelist)`：**只在连接器白名单域名工作**（§6）——host 锚定，
  防 `evil.com/tiktok.com/…` 路径注入与 `tiktok.com.evil.com` 后缀伪装。
- `classify_browser_challenge(signal)` + `is_blocking_challenge`：登录失效/验证码/设备确认/
  内容警告/风控**一律进入 WAITING_FOR_HUMAN**（§6/§13：暂停并通知，**绝不绕过/盲点**）。
- `preferred_selector(available)`：§6 选择器优先级 role/label/test-id，坐标只做最后回退。
- `canary_ok` / `should_disable_connector`：页面结构契约（Canary）——必需选择器缺失即判定
  页面结构变了 → 自动禁用 Connector（§6）。

**红线**：验证码/挑战**绝不自动绕过**（转人工）；只在白名单域名工作。真实 Playwright 驱动
真实账号是 stop-condition，本层只是纯策略，不驱动真实浏览器。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum

# 严格主机名（LDH：字母/数字/连字符 + 点分标签，标签首尾为字母数字，无空标签）。
# 任何含 %、下划线、空白、控制符、编码字节的"host"都不匹配 → 失败即拒（fail-closed），
# 挡住 `evil.com%2f.tiktok.com` / `evil.com%00.tiktok.com` 这类编码差异绕过。
_HOST_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*")


class BrowserChallengeKind(StrEnum):
    """§6 浏览器发布途中可能遇到的挑战——全部阻塞、转人工。"""

    LOGIN_EXPIRED = "LOGIN_EXPIRED"
    CAPTCHA = "CAPTCHA"
    DEVICE_CONFIRM = "DEVICE_CONFIRM"
    CONTENT_WARNING = "CONTENT_WARNING"
    RISK_CONTROL = "RISK_CONTROL"


class SelectorStrategy(StrEnum):
    """§6 选择器策略（优先级从高到低）。"""

    ROLE = "ROLE"
    LABEL = "LABEL"
    TEST_ID = "TEST_ID"
    CSS = "CSS"
    COORDINATE = "COORDINATE"  # 只做最后回退


_SELECTOR_PRIORITY: tuple[SelectorStrategy, ...] = (
    SelectorStrategy.ROLE, SelectorStrategy.LABEL, SelectorStrategy.TEST_ID,
    SelectorStrategy.CSS, SelectorStrategy.COORDINATE,
)

_CHALLENGE_KEYS: dict[BrowserChallengeKind, tuple[str, ...]] = {
    BrowserChallengeKind.LOGIN_EXPIRED: (
        "login", "log in", "登录", "登陆", "sign in", "signin", "登入", "please sign",
        "会话过期", "session expired", "session has expired", "logged out",
        "authentication required", "未登录", "重新登录", "重新登陆",
    ),
    BrowserChallengeKind.CAPTCHA: (
        "captcha", "验证码", "slider", "滑块", "拼图", "verify you are human", "人机验证",
    ),
    BrowserChallengeKind.DEVICE_CONFIRM: (
        "device", "设备确认", "确认设备", "trust this device", "扫码确认", "二次确认",
    ),
    BrowserChallengeKind.CONTENT_WARNING: (
        "content warning", "内容警告", "违规", "policy", "社区规范", "不适宜", "涉嫌",
    ),
    BrowserChallengeKind.RISK_CONTROL: (
        "风控", "risk", "abnormal", "异常", "安全验证", "security check",
    ),
}


def _extract_host(url: str) -> str:
    """从 URL 抽 host——与 **WHATWG（浏览器/Playwright）一致**，防解析差异绕过白名单。

    - 先剥离 WHATWG 会删除的 ASCII tab/换行/回车（否则 `evil.com\\t.tiktok.com` 类差异）。
    - **反斜杠 `\\` 按 `/` 处理**（WHATWG authority 终止符——`evil.com\\.tiktok.com/x` 的真实
      host 是 evil.com，不是 tiktok 子域）。
    - authority 止于首个 `/`、`?`、`#`（fragment `evil.com#@tiktok.com` 真实 host 是 evil.com）。
    - 再去 userinfo(`@`) 与端口(`:`)。
    """
    u = url.strip().lower()
    for ch in ("\t", "\n", "\r"):
        u = u.replace(ch, "")
    u = u.replace("\\", "/")  # WHATWG：反斜杠等价 /
    if "://" in u:
        u = u.split("://", 1)[1]
    for sep in ("/", "?", "#"):  # authority 终止符
        u = u.split(sep, 1)[0]
    u = u.split("@")[-1]  # 去 userinfo（host 在最后一个 @ 之后）
    u = u.split(":", 1)[0]  # 去端口
    return u


def is_domain_allowed(url: str, whitelist: Iterable[str]) -> bool:
    """§6：host 锚定的白名单校验。host == 白名单域 或 是其子域才允许。

    防 `evil.com/tiktok.com/x`（host=evil.com）与 `tiktok.com.evil.com`（后缀是 evil.com）。
    """
    host = _extract_host(url)
    # fail-closed：只有干净的 LDH 主机名才继续判定；含 %/编码字节/空标签等一律拒
    # （WHATWG 对 evil.com%2f.tiktok.com / evil.com%00.tiktok.com 直接抛错，浏览器无法导航）。
    if not host or not _HOST_RE.fullmatch(host):
        return False
    wl = {d.strip().lower().lstrip(".") for d in whitelist if d.strip()}
    return any(host == d or host.endswith("." + d) for d in wl)


def classify_browser_challenge(signal: str) -> BrowserChallengeKind | None:
    """把浏览器页面信号（文本）分类为挑战类型；无匹配 → None（正常）。"""
    hay = signal.lower()
    for kind, keys in _CHALLENGE_KEYS.items():
        if any(k in hay for k in keys):
            return kind
    return None


def is_blocking_challenge(kind: BrowserChallengeKind | None) -> bool:
    """§6/§13：任何已识别的挑战都阻塞（转 WAITING_FOR_HUMAN，绝不绕过）。"""
    return kind is not None


def preferred_selector(available: Iterable[SelectorStrategy]) -> SelectorStrategy | None:
    """§6：按优先级返回可用的最优选择器（坐标最后）；无可用 → None。"""
    avail = set(available)
    for strat in _SELECTOR_PRIORITY:
        if strat in avail:
            return strat
    return None


def canary_ok(
    observed_selectors: Iterable[str], required_selectors: Iterable[str],
) -> bool:
    """§6 页面结构契约：所有必需选择器都在观察到的集合里才算通过。"""
    return set(required_selectors) <= set(observed_selectors)


def should_disable_connector(canary_passed: bool) -> bool:
    """§6：Canary 失败（页面结构变了）→ 自动禁用 Connector。"""
    return not canary_passed
