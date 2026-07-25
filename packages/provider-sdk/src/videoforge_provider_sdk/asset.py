"""素材源端口 + Fake（docs/modules/42 §6）。

真实素材来源（自有库语义检索/商业 Stock/AI 生成/数字人）属停止条件延后：Unconfigured*Provider
诚实返回 UNCONFIGURED；Fake*Provider 按 fixture 回放候选（含许可信息，绝不伪造 license）。
候选评分/五级优先级/护栏均在纯域（domain.resolve_asset_plan/validate_asset_plan），故本端口
contracts-only、不依赖 domain。每次都新建 AssetCandidateSpec，无录制、无共享可变态。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import AssetLicense, AssetSource


class AssetSourceStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"


class AssetSourceErrorCode(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    LICENSE_UNAVAILABLE = "LICENSE_UNAVAILABLE"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class AssetSearchRequest:
    query: str
    role: str  # AssetRole.value
    aspect_ratio: str
    limit: int = 10


@dataclass(frozen=True)
class AssetCandidateSpec:
    """provider 侧的最小候选视图（domain.AssetCandidate 由本层组装或映射得来）。"""

    asset_id: str
    source: AssetSource
    license: AssetLicense  # 诚实携带；未来 provider 不得给出无许可候选
    query: str
    provider: str
    semantic: float = 0.0
    composition: float = 0.0
    resolution: float = 0.0
    motion: float = 0.0
    color: float = 0.0
    brand_ok: float = 1.0
    reuse_count: int = 0


@dataclass
class AssetSourceResult:
    status: AssetSourceStatus
    provider: str
    candidates: list[AssetCandidateSpec] = field(default_factory=list)
    error_code: AssetSourceErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == AssetSourceStatus.OK


@runtime_checkable
class AssetSourceProvider(Protocol):
    name: str
    source: AssetSource  # 该 provider 属哪一级
    execution_location: str

    def search(self, request: AssetSearchRequest) -> AssetSourceResult:
        """按 query/role/aspect_ratio 搜候选素材；候选必须自带 license。"""
        ...

    def health_check(self) -> AssetSourceResult: ...


class UnconfiguredAssetSourceProvider:
    """默认：真实素材源未接入。返回 UNCONFIGURED，不静默假装。"""

    def __init__(
        self,
        source: AssetSource,
        *,
        name: str | None = None,
        execution_location: str = "cloud",
    ) -> None:
        self.source = source
        self.name = name or f"asset.{source.value.lower()}.unconfigured"
        self.execution_location = execution_location

    def search(self, request: AssetSearchRequest) -> AssetSourceResult:
        return AssetSourceResult(
            status=AssetSourceStatus.UNCONFIGURED,
            provider=self.name,
            error_code=AssetSourceErrorCode.UNCONFIGURED,
            detail=f"素材源 {self.source.value} 未接入（需真实库/API/模型）；请人工挑选或稍后重试",
        )

    def health_check(self) -> AssetSourceResult:
        return AssetSourceResult(status=AssetSourceStatus.UNCONFIGURED, provider=self.name)


class FakeAssetSourceProvider:
    """确定性 Fake：回放注册的候选池（按 role 索引），返回时深拷贝以避免调用方回写污染。"""

    def __init__(
        self,
        source: AssetSource,
        *,
        name: str | None = None,
        execution_location: str = "cloud",
        pool: dict[str, list[AssetCandidateSpec]] | None = None,
    ) -> None:
        self.source = source
        self.name = name or f"asset.{source.value.lower()}.fake"
        self.execution_location = execution_location
        # 深拷贝入参 pool 的 license（Pydantic ContractModel 可写），避免调用方回写自己持有的
        # license 对象污染内部池——合规审计负载不容外部改写。AssetCandidateSpec 本身是 frozen
        # dataclass，其他字段是不可变值类型；只需替换 license 为深拷贝副本。
        self._pool: dict[str, list[AssetCandidateSpec]] = {
            role: [replace(s, license=s.license.model_copy(deep=True)) for s in specs]
            for role, specs in (pool or {}).items()
        }

    def search(self, request: AssetSearchRequest) -> AssetSourceResult:
        pool = self._pool.get(request.role, [])
        cands = [
            AssetCandidateSpec(
                asset_id=c.asset_id,
                source=c.source,
                license=c.license.model_copy(deep=True),  # 许可诚实拷贝，绝不被外部改写
                query=request.query,
                provider=self.name,
                semantic=c.semantic,
                composition=c.composition,
                resolution=c.resolution,
                motion=c.motion,
                color=c.color,
                brand_ok=c.brand_ok,
                reuse_count=c.reuse_count,
            )
            for c in pool[: request.limit]
        ]
        return AssetSourceResult(status=AssetSourceStatus.OK, provider=self.name, candidates=cands)

    def health_check(self) -> AssetSourceResult:
        return AssetSourceResult(status=AssetSourceStatus.OK, provider=self.name)


__all__ = [
    "AssetCandidateSpec",
    "AssetSearchRequest",
    "AssetSourceErrorCode",
    "AssetSourceProvider",
    "AssetSourceResult",
    "AssetSourceStatus",
    "FakeAssetSourceProvider",
    "UnconfiguredAssetSourceProvider",
]
