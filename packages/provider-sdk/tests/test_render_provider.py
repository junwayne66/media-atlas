"""RenderProvider 端口：Unconfigured LICENSE_PENDING（Remotion 许可红线）+ Fake 不触真实运行时。"""

import sys
from datetime import UTC, datetime

from videoforge_contracts import (
    RemotionComposition,
    RemotionProp,
    RemotionRenderRequest,
)
from videoforge_provider_sdk import (
    FakeRemotionRenderProvider,
    RenderProvider,
    RenderProviderErrorCode,
    RenderProviderResult,
    RenderProviderStatus,
    UnconfiguredRemotionRenderProvider,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _request() -> RemotionRenderRequest:
    return RemotionRenderRequest(
        id="req-0",
        timeline_id="tl-0",
        composition=RemotionComposition.CAPTIONS,
        props=[
            RemotionProp(
                key="captions",
                value=[
                    {"text": "hello", "start_ms": 0, "end_ms": 1000},
                ],
            )
        ],
        duration_ms=45000,
        fps=30,
        width=1080,
        height=1920,
        entry_component_path="/staging/remotion/Root.tsx",
        output_path="/staging/out/captions.mp4",
        tool_version="remotion-4.0.240",
    )


def test_protocol_conformance() -> None:
    assert isinstance(FakeRemotionRenderProvider(), RenderProvider)
    assert isinstance(UnconfiguredRemotionRenderProvider(), RenderProvider)


def test_unconfigured_license_pending_by_default() -> None:
    # 默认 license_pending=True —— Remotion 许可评审未通过前不接入
    prov = UnconfiguredRemotionRenderProvider()
    result = prov.render(_request())
    assert result.status is RenderProviderStatus.LICENSE_PENDING
    assert result.error_code is RenderProviderErrorCode.LICENSE_PENDING
    assert result.manifest is None  # 绝不静默造 manifest
    assert "许可" in (result.detail or "")


def test_unconfigured_can_be_configured_without_license_pending() -> None:
    # 一旦许可评审通过，可以升级为普通 UNCONFIGURED（等待实际 provider 接入）
    prov = UnconfiguredRemotionRenderProvider(license_pending=False)
    result = prov.render(_request())
    assert result.status is RenderProviderStatus.UNCONFIGURED
    assert result.error_code is RenderProviderErrorCode.UNCONFIGURED


def test_fake_returns_manifest_without_running_remotion() -> None:
    # Fake 严守红线：不 import remotion / 不启子进程
    fake = FakeRemotionRenderProvider(tool_version="remotion-fake-0.0.1")
    result: RenderProviderResult = fake.render(_request())
    assert result.ok and result.manifest is not None
    m = result.manifest
    assert m.request.id == "req-0"
    assert m.tool_version == "remotion-fake-0.0.1"
    assert m.output_digest is None  # Fake 未真实渲染 → 无 output_digest
    # 探针：sys.modules 里没有 remotion 相关包引入
    assert not any(name.startswith("remotion") for name in sys.modules)


def test_fake_returns_recorded_output_digest() -> None:
    # 允许外部 pre-rendered 场景：调用方登记摘要后 Fake 一并返回
    fake = FakeRemotionRenderProvider()
    fake.record_output("req-0", "d" * 64)
    result = fake.render(_request())
    assert result.manifest.output_digest == "d" * 64


def test_fake_render_count_increments() -> None:
    fake = FakeRemotionRenderProvider()
    fake.render(_request())
    fake.render(_request())
    assert fake.render_count == 2
