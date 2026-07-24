"""P5 Exit —— 挑战必停给人工，绝不盲点（§13 / §6 / §7.2）。

浏览器/真机/官方 API 遇到 登录失效/验证码/设备确认/内容警告/授权/风控 → CHALLENGE 或
AUTH_REQUIRED，上层转 WAITING_FOR_HUMAN，**绝不产生外部帖子**（没有绕过去发布）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from p5_flow import run_publish

from videoforge_contracts import PublishState
from videoforge_domain import (
    classify_browser_challenge,
    is_blocking_challenge,
    to_waiting_for_human,
)
from videoforge_provider_sdk import (
    FakeAndroidPublishExecutor,
    FakeBrowserPublishExecutor,
    FakeDouyinPublishExecutor,
    FakeTikTokPublishExecutor,
    PublishExecStatus,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)

# 非 OK（须停/降级）的状态
_NON_OK = {
    PublishExecStatus.CHALLENGE, PublishExecStatus.AUTH_REQUIRED,
    PublishExecStatus.FAILED, PublishExecStatus.UNCONFIGURED,
}


def _assert_paused_no_publish(executor):
    """执行发布流程；遇挑战/授权 → 不发布、无外部帖子，Job 可转 WAITING_FOR_HUMAN。"""
    job, sub = run_publish(executor)
    assert sub.status in _NON_OK
    assert sub.external_post_id is None  # 绝没有绕过去发布
    # Job 未提交（仍 UPLOADING）→ 可安全转人工
    assert job.state is PublishState.UPLOADING
    paused = to_waiting_for_human(job, now=_T0)
    assert paused.state is PublishState.WAITING_FOR_HUMAN
    assert paused.external_post_id is None


def test_browser_challenges_pause_to_human():
    for signal in ("请重新登录", "验证码 captcha", "设备确认", "内容警告：涉嫌违规", "风控"):
        _assert_paused_no_publish(FakeBrowserPublishExecutor(challenge_signal=signal))


def test_browser_non_whitelisted_domain_refused():
    job, sub = run_publish(FakeBrowserPublishExecutor(allowed=False))
    assert sub.status is PublishExecStatus.FAILED
    assert sub.external_post_id is None


def test_android_device_confirm_and_not_ready_pause():
    _assert_paused_no_publish(FakeAndroidPublishExecutor(device_confirm_required=True))
    # 就绪门未过 → FAILED 不发布
    job, sub = run_publish(FakeAndroidPublishExecutor(device_ready=False))
    assert sub.status is PublishExecStatus.FAILED and sub.external_post_id is None


def test_official_api_challenge_and_auth_pause():
    _assert_paused_no_publish(FakeTikTokPublishExecutor(challenge=True))
    _assert_paused_no_publish(FakeTikTokPublishExecutor(auth_required=True))
    _assert_paused_no_publish(FakeDouyinPublishExecutor(challenge=True))


def test_challenge_classification_all_blocking():
    # 每种浏览器挑战信号都被判为阻塞（转人工），正常页面不阻塞
    for sig in ("please log in again", "captcha", "设备确认", "内容警告", "风控异常"):
        assert is_blocking_challenge(classify_browser_challenge(sig)), sig
    assert not is_blocking_challenge(
        classify_browser_challenge("upload complete, ready to publish"))
