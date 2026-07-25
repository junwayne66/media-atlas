"""VF-505 provider-sdk 浏览器发布：Unconfigured / Fake（白名单拒绝 + 挑战暂停 + 幂等）。"""

from datetime import UTC, datetime

from videoforge_contracts import PublishMethod, PublishPlatform, PublishState
from videoforge_domain import new_publish_job
from videoforge_provider_sdk import (
    FakeBrowserPublishExecutor,
    PublishExecErrorCode,
    PublishExecStatus,
    PublishExecutor,
    UnconfiguredBrowserPublishExecutor,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _job():
    return new_publish_job(
        id="j",
        account_id="a",
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.BROWSER_AUTOMATION,
        render_digest="r",
        metadata_digest="m",
        scheduled_window="immediate",
        created_at=_T0,
    ).model_copy(update={"state": PublishState.UPLOADING})


def test_providers_satisfy_protocol():
    assert isinstance(FakeBrowserPublishExecutor(), PublishExecutor)
    assert isinstance(UnconfiguredBrowserPublishExecutor(), PublishExecutor)


def test_unconfigured_never_publishes():
    ex = UnconfiguredBrowserPublishExecutor()
    assert ex.submit(_job()).status is PublishExecStatus.UNCONFIGURED
    assert "浏览器" in ex.creator_info().detail


def test_non_whitelisted_domain_refused():
    # §6：目标域名不在连接器白名单 → 拒绝发布，绝不发布
    ex = FakeBrowserPublishExecutor(allowed=False)
    r = ex.submit(_job())
    assert r.status is PublishExecStatus.FAILED
    assert r.external_post_id is None
    assert ex.creator_info().status is PublishExecStatus.FAILED


def test_challenge_pauses_never_bypasses():
    # §6/§13：登录失效/验证码/设备确认/内容警告 → CHALLENGE（转人工），绝不绕过
    for signal in ("请重新登录", "验证码", "设备确认", "内容警告"):
        r = FakeBrowserPublishExecutor(challenge_signal=signal).submit(_job())
        assert r.status is PublishExecStatus.CHALLENGE
        assert r.error_code is PublishExecErrorCode.CHALLENGE
        assert r.external_post_id is None  # 没有绕过去发布


def test_allowed_no_challenge_is_idempotent():
    ex = FakeBrowserPublishExecutor()  # allowed=True, no challenge
    job = _job()
    a = ex.submit(job)
    b = ex.submit(job)
    assert a.status is PublishExecStatus.OK
    assert a.external_post_id == b.external_post_id
    assert b.idempotent_replay is True


def test_query_status_after_submit():
    ex = FakeBrowserPublishExecutor()
    job = _job()
    ex.submit(job)
    st = ex.query_status(job)
    assert st.found_post and st.external_post_id
