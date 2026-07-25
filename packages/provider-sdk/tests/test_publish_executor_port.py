"""VF-503 provider-sdk 发布执行：Unconfigured / Fake 幂等 / 挑战 / 零 live network。"""

import ast
import inspect
from datetime import UTC, datetime

import videoforge_provider_sdk.publish_executor as pe_module
from videoforge_contracts import PublishJob, PublishMethod, PublishPlatform, PublishState
from videoforge_domain import new_publish_job
from videoforge_provider_sdk import (
    FakeTikTokPublishExecutor,
    PublishExecStatus,
    PublishExecutor,
    UnconfiguredTikTokPublishExecutor,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _job(window: str = "immediate") -> PublishJob:
    return new_publish_job(
        id="j",
        account_id="a",
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.OFFICIAL_API,
        render_digest="r",
        metadata_digest="m",
        scheduled_window=window,
        created_at=_T0,
    ).model_copy(update={"state": PublishState.UPLOADING})


def test_providers_satisfy_protocol():
    assert isinstance(FakeTikTokPublishExecutor(), PublishExecutor)
    assert isinstance(UnconfiguredTikTokPublishExecutor(), PublishExecutor)


def test_unconfigured_never_publishes():
    ex = UnconfiguredTikTokPublishExecutor()
    assert ex.submit(_job()).status is PublishExecStatus.UNCONFIGURED
    assert ex.creator_info().status is PublishExecStatus.UNCONFIGURED
    assert ex.query_status(_job()).status is PublishExecStatus.UNCONFIGURED


def test_fake_submit_is_idempotent_by_key():
    ex = FakeTikTokPublishExecutor()
    job = _job()
    a = ex.submit(job)
    b = ex.submit(job)  # 同 idempotency_key 再次提交
    assert a.status is PublishExecStatus.OK
    assert a.external_post_id == b.external_post_id  # 同一帖子
    assert b.idempotent_replay is True  # 未重复发布


def test_fake_different_jobs_get_different_posts():
    ex = FakeTikTokPublishExecutor()
    a = ex.submit(_job(window="w1"))
    b = ex.submit(_job(window="w2"))  # 不同 key
    assert a.external_post_id != b.external_post_id


def test_fake_challenge_and_auth_route_to_status():
    assert (
        FakeTikTokPublishExecutor(challenge=True).submit(_job()).status
        is PublishExecStatus.CHALLENGE
    )
    assert (
        FakeTikTokPublishExecutor(auth_required=True).submit(_job()).status
        is PublishExecStatus.AUTH_REQUIRED
    )
    assert (
        FakeTikTokPublishExecutor(auth_required=True).creator_info().status
        is PublishExecStatus.AUTH_REQUIRED
    )


def test_fake_query_status_finds_after_submit():
    ex = FakeTikTokPublishExecutor()
    job = _job()
    ex.submit(job)
    st = ex.query_status(job)
    assert st.found_post is True and st.external_post_id


def test_fake_query_status_preexisting_reconciliation():
    # 模拟"提交前平台已有匹配帖子" → 对账场景
    ex = FakeTikTokPublishExecutor(preexisting=True)
    st = ex.query_status(_job())
    assert st.found_post is True


def test_module_has_zero_network_imports():
    tree = ast.parse(inspect.getsource(pe_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {"__future__", "dataclasses", "enum", "typing", "videoforge_contracts"}
    assert imported <= allowed, f"发布执行器引入了非白名单模块: {imported - allowed}"
