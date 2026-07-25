"""发布链真库端到端：幂等建任务 / 预检 / 提交 / 对账 / 人工完成。

三条红线的**非空跑**证明：
- 双 submit：第二次被 domain 幂等硬拦（HTTP 409），且 attempts 仍只有一条 token；
- 挑战：executor 返回 CHALLENGE → WAITING_FOR_HUMAN 且 `external_post_id is None`（没绕过发布）；
- 对账：查到已存在帖子 → SUCCEEDED_RECONCILED，attempts 数量**不变**（没有第二次提交）。
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from videoforge_api.main import create_app
from videoforge_api.publish import (
    DbPublishGateway,
    ManualCompleteRequest,
    PreflightRequest,
    PublishJobCreate,
)
from videoforge_api.settings import Settings
from videoforge_contracts import (
    AccountStatus,
    AuthStatus,
    PublishMediaProbe,
    PublishMetadata,
    PublishPlatform,
    PublishState,
)
from videoforge_provider_sdk.publish_connector import FakePublishConnector
from videoforge_provider_sdk.publish_executor import (
    FakeDouyinPublishExecutor,
    FakeTikTokPublishExecutor,
)

_NEW_TABLES = ("creative_documents", "review_decisions", "publish_jobs", "performance_snapshots")
_NOW = datetime(2026, 7, 25, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_new_tables(migrated_engine: Engine) -> Iterator[None]:
    yield
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_NEW_TABLES)} CASCADE"))


def _metadata() -> PublishMetadata:
    return PublishMetadata(
        title="AI 芯片实测", description="三点结论", tags=["ai"], language="zh-CN"
    )


def _create_request(**overrides) -> PublishJobCreate:
    kwargs = {
        "account_id": "acct-1",
        "platform": PublishPlatform.TIKTOK,
        "media_digest": "e" * 64,
        "metadata": _metadata(),
    }
    kwargs.update(overrides)
    return PublishJobCreate(**kwargs)


def _good_probe() -> PublishMediaProbe:
    return PublishMediaProbe(
        width=1080,
        height=1920,
        aspect_ratio="9:16",
        video_codec="h264",
        audio_codec="aac",
        container="mp4",
        file_size_bytes=20 * 1024 * 1024,
        duration_ms=45_000,
    )


def _gateway(engine: Engine, **executor_kwargs) -> DbPublishGateway:
    return DbPublishGateway(
        engine,
        executors={
            PublishPlatform.TIKTOK: FakeTikTokPublishExecutor(**executor_kwargs),
            PublishPlatform.DOUYIN: FakeDouyinPublishExecutor(**executor_kwargs),
        },
    )


def test_create_is_idempotent_and_copy_index_derives_new_job(migrated_engine: Engine):
    gw = _gateway(migrated_engine)
    job, created = gw.create(_create_request())
    assert created and job.state is PublishState.PENDING

    same, created_again = gw.create(_create_request())
    assert not created_again and same.id == job.id  # 同内容绝不建第二个任务

    copy, copy_created = gw.create(_create_request(copy_index=1))
    assert copy_created and copy.id != job.id
    assert copy.idempotency_key != job.idempotency_key
    assert copy.scheduled_window.endswith("#copy1")
    assert not gw.get(copy.id).issues  # 派生键仍与 Job 字段自洽（护栏空）


def test_submit_then_reconcile_never_double_publishes(migrated_engine: Engine):
    gw = _gateway(migrated_engine)
    job, _ = gw.create(_create_request())

    submitted = gw.submit(job.id)
    assert submitted.job.state is PublishState.SUBMITTED
    assert len(submitted.job.attempts) == 1
    token = submitted.job.attempts[0].external_post_token

    reconciled = gw.reconcile(job.id)
    assert reconciled.job.state is PublishState.SUCCEEDED_RECONCILED
    assert reconciled.found_post and reconciled.job.external_post_id
    # 对账没有新增 attempt —— 没有第二次提交
    assert reconciled.attempts_count == 1
    assert reconciled.job.attempts[0].external_post_token == token
    assert not gw.get(job.id).issues


def test_second_submit_is_blocked(migrated_engine: Engine):
    gw = _gateway(migrated_engine)
    job, _ = gw.create(_create_request())
    gw.submit(job.id)

    from videoforge_domain.publish_job import IllegalPublishTransition

    with pytest.raises(IllegalPublishTransition):
        gw.submit(job.id)
    stored = gw.get(job.id)
    assert len([a for a in stored.job.attempts if a.external_post_token]) == 1
    assert not stored.issues  # 无 DOUBLE_SUBMIT


def test_recovery_from_waiting_for_human_still_cannot_republish(migrated_engine: Engine):
    """人工恢复回路（WAITING_FOR_HUMAN → UPLOADING 是合法边）仍被 durable token latch 挡住。

    这正是 VF-503 verifier 警告的落地风险：只要 attempts 的 external_post_token 在往返中
    幸存，`can_submit` 就恒为 False——即使状态机允许重回 UPLOADING。
    """
    from videoforge_domain.publish_job import IllegalPublishTransition, to_waiting_for_human
    from videoforge_persistence import session_scope
    from videoforge_persistence.publish import PublishJobRepository

    gw = _gateway(migrated_engine)
    job, _ = gw.create(_create_request(media_digest="c" * 64))
    submitted = gw.submit(job.id).job

    with session_scope(migrated_engine) as s:
        repo = PublishJobRepository(s)
        stored = repo.get(job.id)
        repo.update(
            to_waiting_for_human(stored.job, now=_NOW), expected_row_version=stored.row_version
        )

    with pytest.raises(IllegalPublishTransition) as exc:
        gw.submit(job.id)
    assert "已提交过" in str(exc.value)
    after = gw.get(job.id).job
    assert [a.external_post_token for a in after.attempts] == [
        submitted.attempts[0].external_post_token
    ]


def test_challenge_routes_to_human_without_publishing(migrated_engine: Engine):
    gw = _gateway(migrated_engine, challenge=True)
    job, _ = gw.create(_create_request())

    result = gw.submit(job.id)
    assert result.job.state is PublishState.WAITING_FOR_HUMAN
    assert result.job.external_post_id is None  # 绝不绕过挑战发布
    assert result.job.attempts == []


def test_manual_complete_only_from_waiting_for_human(migrated_engine: Engine):
    from videoforge_domain.publish_job import IllegalPublishTransition

    gw = _gateway(migrated_engine, challenge=True)
    job, _ = gw.create(_create_request())
    gw.submit(job.id)
    done = gw.manual_complete(job.id, ManualCompleteRequest(external_post_id="human-post-1"))
    assert done.state is PublishState.SUCCEEDED_RECONCILED
    assert done.external_post_id == "human-post-1"
    assert done.attempts == []  # 人工完成不新增提交

    ok_gw = _gateway(migrated_engine)
    fresh, _ = ok_gw.create(_create_request(media_digest="f" * 64))
    with pytest.raises(IllegalPublishTransition):
        ok_gw.manual_complete(fresh.id, ManualCompleteRequest(external_post_id="x"))


def test_preflight_blocks_job_when_media_violates_spec(migrated_engine: Engine):
    gw = _gateway(migrated_engine)
    job, _ = gw.create(_create_request())
    bad = _good_probe().model_copy(update={"container": "avi", "duration_ms": 1_000})

    result = gw.preflight(job.id, PreflightRequest(probe=bad, metadata=_metadata()))
    assert not result.report.publishable
    assert result.job.state is PublishState.PREFLIGHT_BLOCKED
    checks = {str(f.check) for f in result.report.findings}
    assert {"CONTAINER", "DURATION"} <= checks


def test_preflight_passes_and_blocks_on_unauthorized_connector(migrated_engine: Engine):
    ok_gw = DbPublishGateway(
        migrated_engine,
        executors={PublishPlatform.TIKTOK: FakeTikTokPublishExecutor()},
    )
    job, _ = ok_gw.create(_create_request())
    passed = ok_gw.preflight(job.id, PreflightRequest(probe=_good_probe(), metadata=_metadata()))
    assert passed.report.publishable and passed.job.state is PublishState.PENDING

    blocked_gw = DbPublishGateway(
        migrated_engine,
        executors={PublishPlatform.TIKTOK: FakeTikTokPublishExecutor()},
        connectors={
            PublishPlatform.TIKTOK: FakePublishConnector(
                platform=PublishPlatform.TIKTOK,
                auth_status=AuthStatus.EXPIRED,
                account_status=AccountStatus.SUSPENDED,
            )
        },
    )
    other, _ = blocked_gw.create(_create_request(media_digest="a" * 64))
    result = blocked_gw.preflight(
        other.id, PreflightRequest(probe=_good_probe(), metadata=_metadata())
    )
    assert not result.report.publishable  # 未授权 + 账号封禁绝不可发


# --- HTTP 面：状态码语义 -------------------------------------------------------


@pytest.fixture()
def client(migrated_engine: Engine) -> Iterator[TestClient]:
    url = migrated_engine.url.render_as_string(hide_password=False)
    app = create_app(Settings(database_url=url))
    app.state.publish_gateway = _gateway(migrated_engine)
    with TestClient(app) as c:
        yield c


def test_http_double_submit_returns_409(client: TestClient):
    created = client.post(
        "/v1/publish-jobs",
        json={
            "account_id": "acct-http",
            "platform": "TIKTOK",
            "media_digest": "b" * 64,
            "metadata": _metadata().model_dump(mode="json"),
        },
    )
    assert created.status_code == 201
    job_id = created.json()["id"]

    again = client.post(
        "/v1/publish-jobs",
        json={
            "account_id": "acct-http",
            "platform": "TIKTOK",
            "media_digest": "b" * 64,
            "metadata": _metadata().model_dump(mode="json"),
        },
    )
    assert again.status_code == 200 and again.json()["id"] == job_id  # 幂等命中

    assert client.post(f"/v1/publish-jobs/{job_id}/submit").status_code == 200
    second = client.post(f"/v1/publish-jobs/{job_id}/submit")
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert "SUBMITTED" in detail or "幂等" in detail  # 域拒绝的原文透传

    view = client.get(f"/v1/publish-jobs/{job_id}").json()
    assert len(view["job"]["attempts"]) == 1  # 响应里 attempts 完整可见
    assert view["issues"] == []


def test_http_publish_calendar_next(client: TestClient):
    resp = client.get(
        "/v1/publish-calendar/next",
        params={"window": "22:00-02:00", "now": "2026-07-25T23:30:00+00:00"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["immediate"] is True  # 跨零点窗口内 → 立即

    later = client.get(
        "/v1/publish-calendar/next",
        params={"window": "19:00-23:00", "now": "2026-07-25T09:00:00+00:00"},
    ).json()
    assert later["immediate"] is False
    assert later["next_publish_time"].startswith("2026-07-25T19:00")

    bad = client.get("/v1/publish-calendar/next", params={"window": "not-a-window"})
    assert bad.status_code == 422
