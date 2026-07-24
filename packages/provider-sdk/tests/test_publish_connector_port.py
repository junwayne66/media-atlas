"""VF-502 provider-sdk 发布连接器：Unconfigured 诚实不可用 / Fake 上报注入能力 / 零网络。"""

import ast
import inspect

import videoforge_provider_sdk.publish_connector as pc_module
from videoforge_contracts import (
    AccountStatus,
    AuthStatus,
    ClientReviewStatus,
    PublishMethod,
    PublishPlatform,
)
from videoforge_provider_sdk import (
    FakePublishConnector,
    PublishConnector,
    UnconfiguredPublishConnector,
)


def test_providers_satisfy_protocol():
    assert isinstance(
        FakePublishConnector(platform=PublishPlatform.TIKTOK), PublishConnector)
    assert isinstance(
        UnconfiguredPublishConnector(platform=PublishPlatform.TIKTOK), PublishConnector)


def test_unconfigured_reports_unavailable_and_unauthorized():
    cap = UnconfiguredPublishConnector(platform=PublishPlatform.TIKTOK).capabilities()
    assert cap.available is False
    assert cap.auth_status is AuthStatus.UNAUTHORIZED
    assert cap.account_status is AccountStatus.UNKNOWN


def test_fake_reports_injected_capabilities():
    conn = FakePublishConnector(
        platform=PublishPlatform.DOUYIN, method=PublishMethod.OFFICIAL_SHARE_SDK,
        auth_status=AuthStatus.PENDING_REVIEW,
        client_review_status=ClientReviewStatus.UNDER_REVIEW,
        account_status=AccountStatus.RESTRICTED,
        max_file_size_bytes=100_000_000,
    )
    cap = conn.capabilities()
    assert cap.platform is PublishPlatform.DOUYIN
    assert cap.method is PublishMethod.OFFICIAL_SHARE_SDK
    assert cap.auth_status is AuthStatus.PENDING_REVIEW
    assert cap.client_review_status is ClientReviewStatus.UNDER_REVIEW
    assert cap.account_status is AccountStatus.RESTRICTED
    assert cap.max_file_size_bytes == 100_000_000


def test_fake_defaults_are_authorized_active():
    cap = FakePublishConnector(platform=PublishPlatform.TIKTOK).capabilities()
    assert cap.available and cap.auth_status is AuthStatus.AUTHORIZED
    assert cap.account_status is AccountStatus.ACTIVE


def test_fake_is_deterministic():
    conn = FakePublishConnector(platform=PublishPlatform.TIKTOK)
    assert conn.capabilities() == conn.capabilities()


def test_module_has_zero_network_imports():
    # 发布连接器只上报能力，绝不触真实平台（零网络/HTTP/subprocess）
    tree = ast.parse(inspect.getsource(pc_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {"__future__", "typing", "videoforge_contracts"}
    assert imported <= allowed, f"发布连接器引入了非白名单模块: {imported - allowed}"
