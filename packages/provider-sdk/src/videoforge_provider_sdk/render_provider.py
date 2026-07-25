"""渲染 Provider 端口 + Fake（docs/modules/42 §8.3；ADR-002 Remotion 特殊许可）。

**许可红线**：Remotion 商业授权对使用者有条款要求，接入真实运行时前必须专项评审。
本端口的 Unconfigured 版本永远返回 UNCONFIGURED；Fake 版本仅回放"渲染成功的清单"，
**绝不真正调用 Remotion CLI / npm / 任何 JS 运行时**。真实实现（GPU worker / 本地 Node）
延后至许可评审通过。

端口 contracts-only（不依赖 domain）——RemotionRenderRequest 与 RemotionRenderManifest 都在
contracts 层；本端口只做请求 → 结果的映射。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import RemotionRenderManifest, RemotionRenderRequest


class RenderProviderStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"
    LICENSE_PENDING = "license_pending"  # 许可评审未通过


class RenderProviderErrorCode(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    LICENSE_PENDING = "LICENSE_PENDING"
    RENDER_FAILED = "RENDER_FAILED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass
class RenderProviderResult:
    status: RenderProviderStatus
    provider: str
    manifest: RemotionRenderManifest | None = None
    error_code: RenderProviderErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == RenderProviderStatus.OK


@runtime_checkable
class RenderProvider(Protocol):
    name: str
    execution_location: str

    def render(self, request: RemotionRenderRequest) -> RenderProviderResult:
        """请求 → 渲染 manifest。未渲染前 manifest 不带 output_digest。"""
        ...

    def health_check(self) -> RenderProviderResult: ...


class UnconfiguredRemotionRenderProvider:
    """默认：Remotion 运行时未接入（等待许可评审）。绝不静默假装。"""

    def __init__(
        self,
        *,
        name: str = "remotion.render.unconfigured",
        execution_location: str = "cloud",
        license_pending: bool = True,
    ) -> None:
        self.name = name
        self.execution_location = execution_location
        self._license_pending = license_pending

    def render(self, request: RemotionRenderRequest) -> RenderProviderResult:
        code = (
            RenderProviderErrorCode.LICENSE_PENDING
            if self._license_pending
            else RenderProviderErrorCode.UNCONFIGURED
        )
        status = (
            RenderProviderStatus.LICENSE_PENDING
            if self._license_pending
            else RenderProviderStatus.UNCONFIGURED
        )
        return RenderProviderResult(
            status=status,
            provider=self.name,
            error_code=code,
            detail=(
                "Remotion 商业许可评审未通过，未接入运行时；请人工手动渲染或稍后重试"
                if self._license_pending
                else "Remotion 渲染 Provider 未配置（缺 npm/CLI 路径）；请稍后重试"
            ),
        )

    def health_check(self) -> RenderProviderResult:
        return RenderProviderResult(
            status=RenderProviderStatus.LICENSE_PENDING
            if self._license_pending
            else RenderProviderStatus.UNCONFIGURED,
            provider=self.name,
        )


class FakeRemotionRenderProvider:
    """确定性 Fake：把请求包成 manifest 返回（**不调 Remotion**）。供上游做端到端测试。

    严格保证：不产生任何子进程、不 import remotion 相关包；返回的 manifest 中：
    - tool_version = 构造时注入
    - output_digest 缺省为 None（表示"未真正渲染"）；只有调用方显式 `record_output` 记录摘要后
      才写入返回值——这样测试可以模拟"外部预先渲染 + 记录哈希"的路径而不引真库。
    """

    def __init__(
        self,
        *,
        name: str = "remotion.render.fake",
        execution_location: str = "local",
        tool_version: str = "remotion-fake-0.0.0",
    ) -> None:
        self.name = name
        self.execution_location = execution_location
        self.tool_version = tool_version
        self._recorded_digests: dict[str, str] = {}
        self._render_count = 0

    def record_output(self, request_id: str, digest: str) -> None:
        """外部预先"渲染"完把 output_digest 塞进来；Fake 不做任何真实渲染。"""
        self._recorded_digests[request_id] = digest

    def render(self, request: RemotionRenderRequest) -> RenderProviderResult:
        self._render_count += 1
        manifest = RemotionRenderManifest(
            id=f"m-{request.id}",
            request=request,
            input_digests={},
            output_digest=self._recorded_digests.get(request.id),
            tool_version=self.tool_version,
            created_at=datetime.fromtimestamp(0),
        )
        return RenderProviderResult(
            status=RenderProviderStatus.OK,
            provider=self.name,
            manifest=manifest,
        )

    @property
    def render_count(self) -> int:
        return self._render_count

    def health_check(self) -> RenderProviderResult:
        return RenderProviderResult(status=RenderProviderStatus.OK, provider=self.name)


__all__ = [
    "FakeRemotionRenderProvider",
    "RenderProvider",
    "RenderProviderErrorCode",
    "RenderProviderResult",
    "RenderProviderStatus",
    "UnconfiguredRemotionRenderProvider",
]
