"""VF-504 抖音发布：错误映射（§3.2 OpenAPI）+ Douyin executor（Fake-first，零网络）。"""

import ast
import inspect
from datetime import UTC, datetime

import videoforge_provider_sdk.publish_errors as pe_module
from videoforge_contracts import PublishMethod, PublishPlatform, PublishState
from videoforge_domain import new_publish_job
from videoforge_provider_sdk import (
    FakeDouyinPublishExecutor,
    PublishExecErrorCode,
    PublishExecStatus,
    UnconfiguredDouyinPublishExecutor,
    map_publish_error,
)

_T0 = datetime(2026, 7, 25, tzinfo=UTC)


def _job(window: str = "immediate"):
    return new_publish_job(
        id="j",
        account_id="a",
        platform=PublishPlatform.DOUYIN,
        method=PublishMethod.OFFICIAL_API,
        render_digest="r",
        metadata_digest="m",
        scheduled_window=window,
        created_at=_T0,
    ).model_copy(update={"state": PublishState.UPLOADING})


# --- §3.2 错误映射 --------------------------------------------------------


def test_auth_errors_map_to_auth_required_human():
    for code, msg in [
        ("2190008", "invalid access_token"),
        ("", "授权过期，请重新授权"),
        ("", "unauthorized"),
        ("", "token expired"),
    ]:
        m = map_publish_error(code, msg)
        assert m.status is PublishExecStatus.AUTH_REQUIRED
        assert m.error_code is PublishExecErrorCode.AUTH_REQUIRED
        assert m.human_required and not m.retryable


def test_risk_challenge_maps_to_challenge_human():
    for msg in ["风控拦截", "需要验证码", "captcha required", "安全验证"]:
        m = map_publish_error("", msg)
        assert m.status is PublishExecStatus.CHALLENGE
        assert m.human_required and not m.retryable


def test_rate_limit_maps_to_retryable():
    for msg in ["触发限流", "rate limit exceeded", "qps 超限", "too many requests"]:
        m = map_publish_error("", msg)
        assert m.error_code is PublishExecErrorCode.RATE_LIMITED
        assert m.retryable and not m.human_required


def test_unknown_maps_to_failed_unknown():
    m = map_publish_error("E_WEIRD", "视频格式不支持")
    assert m.status is PublishExecStatus.FAILED
    assert m.error_code is PublishExecErrorCode.UNKNOWN
    assert not m.human_required and not m.retryable


def test_priority_auth_before_challenge_before_rate():
    # 同时含授权 + 风控 + 限流关键词 → 授权优先（先严先安全）
    m = map_publish_error("", "access_token 过期 且 风控 且 限流")
    assert m.status is PublishExecStatus.AUTH_REQUIRED
    # 风控 + 限流（无授权）→ 风控优先
    m2 = map_publish_error("", "风控 且 限流")
    assert m2.status is PublishExecStatus.CHALLENGE


def test_mapping_is_case_insensitive():
    assert map_publish_error("", "ACCESS_TOKEN EXPIRED").status is (PublishExecStatus.AUTH_REQUIRED)


# --- Douyin executor（Fake-first）----------------------------------------


def test_unconfigured_douyin_never_publishes():
    ex = UnconfiguredDouyinPublishExecutor()
    assert ex.submit(_job()).status is PublishExecStatus.UNCONFIGURED
    assert ex.creator_info().status is PublishExecStatus.UNCONFIGURED
    assert "抖音" in ex.creator_info().detail


def test_fake_douyin_submit_is_idempotent():
    ex = FakeDouyinPublishExecutor()
    job = _job()
    a = ex.submit(job)
    b = ex.submit(job)
    assert a.external_post_id == b.external_post_id
    assert b.idempotent_replay is True


def test_fake_douyin_query_url_is_douyin():
    ex = FakeDouyinPublishExecutor()
    job = _job()
    ex.submit(job)
    assert "douyin.com" in ex.query_status(job).external_url


def test_fake_douyin_error_injections():
    assert (
        FakeDouyinPublishExecutor(challenge=True).submit(_job()).status
        is PublishExecStatus.CHALLENGE
    )
    assert (
        FakeDouyinPublishExecutor(auth_required=True).submit(_job()).status
        is PublishExecStatus.AUTH_REQUIRED
    )
    assert (
        FakeDouyinPublishExecutor(rate_limited=True).submit(_job()).error_code
        is PublishExecErrorCode.RATE_LIMITED
    )


def test_error_mapping_module_zero_network():
    tree = ast.parse(inspect.getsource(pe_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    # 允许 stdlib + 同包（publish_errors 引用同包的 enum），不允许网络/domain
    allowed = {
        "__future__",
        "dataclasses",
        "enum",
        "typing",
        "videoforge_provider_sdk",
        "videoforge_contracts",
    }
    assert imported <= allowed, f"错误映射引入了非白名单模块: {imported - allowed}"
    for banned in ("requests", "httpx", "urllib", "socket", "aiohttp"):
        assert banned not in imported
