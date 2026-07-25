"""VF-601 指标连接器端口测试：诚实 Unconfigured + 确定性 Fake + null 保持 + 零网络。"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime

from videoforge_contracts import (
    AuthStatus,
    MetricField,
    PerformanceSnapshot,
    PublishPlatform,
)
from videoforge_provider_sdk import (
    FakeMetricsConnector,
    MetricsConnector,
    MetricsFetchStatus,
    UnconfiguredMetricsConnector,
)
from videoforge_provider_sdk import metrics_connector as mc_module

_OBS = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _snap(**over) -> PerformanceSnapshot:
    base = dict(
        id="rec", platform=PublishPlatform.TIKTOK, platform_post_id="p1",
        account_id="a1", observed_at=_OBS, age_hours=1.0, source_confidence=0.9,
    )
    base.update(over)
    return PerformanceSnapshot(**base)


def _fetch(conn, *, post="p1", age=1.0):
    return conn.fetch(platform_post_id=post, account_id="a1", observed_at=_OBS,
                       age_hours=age)


# --- 端口一致性 -------------------------------------------------------------

def test_fakes_satisfy_protocol():
    assert isinstance(UnconfiguredMetricsConnector(platform=PublishPlatform.TIKTOK),
                       MetricsConnector)
    assert isinstance(FakeMetricsConnector(platform=PublishPlatform.DOUYIN),
                       MetricsConnector)


# --- Unconfigured 诚实 ------------------------------------------------------

def test_unconfigured_reports_unavailable_and_never_fetches():
    conn = UnconfiguredMetricsConnector(platform=PublishPlatform.TIKTOK)
    cap = conn.capabilities()
    assert cap.available is False
    assert cap.auth_status is AuthStatus.UNAUTHORIZED
    assert cap.provided_fields == []
    r = _fetch(conn)
    assert r.status is MetricsFetchStatus.UNCONFIGURED
    assert r.snapshot is None  # 绝不编造指标


# --- Fake 回放 + null 保持 --------------------------------------------------

def test_fake_replays_recorded_snapshot_and_preserves_null():
    snap = _snap(views=100, likes=5)  # 只给 views/likes，其余 None
    conn = FakeMetricsConnector(
        platform=PublishPlatform.TIKTOK, recorded={("p1", 1.0): snap},
        provided_fields=(MetricField.VIEWS, MetricField.LIKES),
        min_seconds_between_calls=30,
    )
    r = _fetch(conn)
    assert r.status is MetricsFetchStatus.OK
    assert r.snapshot.views == 100 and r.snapshot.likes == 5
    # 缺失字段保持 null（红线）——绝不填 0
    assert r.snapshot.comments is None and r.snapshot.shares is None
    assert r.snapshot.impressions is None and r.snapshot.completion_rate is None
    assert conn.capabilities().min_seconds_between_calls == 30
    assert conn.fetch_count == 1


def test_fake_not_found_when_unrecorded():
    conn = FakeMetricsConnector(platform=PublishPlatform.TIKTOK,
                                 recorded={("p1", 1.0): _snap(views=1)})
    r = _fetch(conn, age=72.0)  # 未录制的年龄
    assert r.status is MetricsFetchStatus.NOT_FOUND and r.snapshot is None


def test_fake_deep_copies_so_caller_mutation_does_not_pollute():
    snap = _snap(views=100)
    conn = FakeMetricsConnector(platform=PublishPlatform.TIKTOK,
                                 recorded={("p1", 1.0): snap})
    first = _fetch(conn).snapshot
    first.views = 999  # 调用方改动返回值
    second = _fetch(conn).snapshot
    assert second.views == 100  # 内部录制不受污染
    # 构造后改动入参也不污染
    snap.views = 777
    assert _fetch(conn).snapshot.views == 100


def test_fake_injected_rate_limit_auth_fail():
    rl = _fetch(FakeMetricsConnector(platform=PublishPlatform.TIKTOK,
                                      rate_limited=True, retry_after_seconds=120))
    assert rl.status is MetricsFetchStatus.RATE_LIMITED
    assert rl.retry_after_seconds == 120 and rl.snapshot is None

    au = _fetch(FakeMetricsConnector(platform=PublishPlatform.TIKTOK,
                                      auth_required=True))
    assert au.status is MetricsFetchStatus.AUTH_REQUIRED and au.snapshot is None

    fa = _fetch(FakeMetricsConnector(platform=PublishPlatform.TIKTOK, fail=True))
    assert fa.status is MetricsFetchStatus.FAILED and fa.snapshot is None


def test_fake_determinism():
    conn = FakeMetricsConnector(platform=PublishPlatform.TIKTOK,
                                 recorded={("p1", 1.0): _snap(views=100, likes=5)})
    a, b = _fetch(conn), _fetch(conn)
    assert (a.status, a.snapshot.views, a.snapshot.likes) == (
        b.status, b.snapshot.views, b.snapshot.likes)


# --- 零网络（红线）---------------------------------------------------------

def test_module_has_zero_network_imports():
    # Fake/Unconfigured 承诺：零网络、零 subprocess——用 AST 检查真实 import。
    tree = ast.parse(inspect.getsource(mc_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {
        "__future__", "dataclasses", "datetime", "enum", "typing",
        "videoforge_contracts",
    }
    forbidden = {"requests", "httpx", "socket", "urllib", "subprocess", "aiohttp"}
    assert imported <= allowed, f"引入了非白名单模块: {imported - allowed}"
    assert not (imported & forbidden)


def test_provider_sdk_does_not_import_domain():
    # 层级：provider-sdk 只依赖 contracts，绝不 import domain。
    src = inspect.getsource(mc_module)
    assert "videoforge_domain" not in src
