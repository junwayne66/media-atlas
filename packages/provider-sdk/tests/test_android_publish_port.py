"""VF-506 provider-sdk Android 真机发布：Unconfigured / Fake（就绪门 + 确认暂停 + 幂等）。"""

from datetime import UTC, datetime

from videoforge_contracts import PublishMethod, PublishPlatform, PublishState
from videoforge_domain import new_publish_job
from videoforge_provider_sdk import (
    FakeAndroidPublishExecutor,
    PublishExecErrorCode,
    PublishExecStatus,
    PublishExecutor,
    UnconfiguredAndroidPublishExecutor,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _job():
    return new_publish_job(
        id="j",
        account_id="acct_9",
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.ANDROID_DEVICE,
        render_digest="r",
        metadata_digest="m",
        scheduled_window="immediate",
        created_at=_T0,
    ).model_copy(update={"state": PublishState.UPLOADING})


def test_providers_satisfy_protocol():
    assert isinstance(FakeAndroidPublishExecutor(), PublishExecutor)
    assert isinstance(UnconfiguredAndroidPublishExecutor(), PublishExecutor)


def test_unconfigured_never_publishes():
    ex = UnconfiguredAndroidPublishExecutor()
    assert ex.submit(_job()).status is PublishExecStatus.UNCONFIGURED
    assert "Android" in ex.creator_info().detail


def test_device_not_ready_refuses():
    # §7.2：就绪门未过（含前台账号错）→ 拒绝发布，绝不发
    r = FakeAndroidPublishExecutor(device_ready=False).submit(_job())
    assert r.status is PublishExecStatus.FAILED
    assert r.external_post_id is None


def test_device_confirm_pauses_to_human():
    # §7.2 步 6：提交前需最终确认 → CHALLENGE，转人工，无产物
    r = FakeAndroidPublishExecutor(device_confirm_required=True).submit(_job())
    assert r.status is PublishExecStatus.CHALLENGE
    assert r.error_code is PublishExecErrorCode.CHALLENGE
    assert r.external_post_id is None


def test_ready_device_idempotent_submit():
    ex = FakeAndroidPublishExecutor()  # device_ready=True, no confirm
    job = _job()
    a = ex.submit(job)
    b = ex.submit(job)
    assert a.status is PublishExecStatus.OK
    assert a.external_post_id == b.external_post_id
    assert b.idempotent_replay is True
