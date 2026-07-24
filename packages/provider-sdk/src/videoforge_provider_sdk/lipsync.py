"""口型同步端口 + Fake（docs/modules/43 §10.2：GPU 局部脸区合成 + 一致性 QA）。

`synthesize(segment, source_video, dub_audio, face_region) -> Audio/VideoArtifact + QA`。
真实 GPU LipSync（MuseTalk 类）需 GPU + 权重（License 待清）→ stop-condition 延后；
`UnconfiguredLipSyncProvider` 恒返 UNCONFIGURED。

**红线**：口型非阻塞。Provider 只负责"尝试合成 + 自评 QA"；**是否降级由 domain 决定**
（QA 不过 → domain 自动走回退阶梯）。`FakeLipSyncProvider` 确定性、**零 GPU/模型/subprocess
导入**（AST 可验），不假装真实口型；QA 可注入以驱动 domain 的降级路径测试。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import LipSyncQAReport


class LipSyncStatus(StrEnum):
    OK = "OK"  # 合成产出（QA 结果见 result.qa，是否采用由 domain 决定）
    FAILED = "FAILED"  # 合成本身失败（无产物）
    UNCONFIGURED = "UNCONFIGURED"
    INELIGIBLE = "INELIGIBLE"  # provider 侧判定不可合成（如无脸）


class LipSyncErrorCode(StrEnum):
    GPU_UNAVAILABLE = "GPU_UNAVAILABLE"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    SYNTHESIS_FAILED = "SYNTHESIS_FAILED"
    FACE_NOT_FOUND = "FACE_NOT_FOUND"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LipSyncRequest:
    """一次局部脸区口型合成请求。"""

    segment_id: str
    start_ms: int
    end_ms: int
    source_video_ref: str
    dub_audio_ref: str
    face_bbox: tuple[float, float, float, float] | None = None  # 归一化 x,y,w,h
    model_hint: str | None = None
    seed: int | None = None


@dataclass(frozen=True)
class LipSyncResult:
    status: LipSyncStatus
    segment_id: str
    synthesized_artifact_id: str | None = None
    qa: LipSyncQAReport | None = None
    error_code: LipSyncErrorCode | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class LipSyncProvider(Protocol):
    """§10.2 GPU LipSync 端口。"""

    name: str

    def synthesize(self, request: LipSyncRequest) -> LipSyncResult: ...

    def health_check(self) -> LipSyncResult: ...


class UnconfiguredLipSyncProvider:
    """诚实占位：无真实 GPU LipSync 引擎/权重，绝不合成（stop-condition 延后）。"""

    def __init__(self, *, name: str = "lipsync.unconfigured") -> None:
        self.name = name

    def synthesize(self, request: LipSyncRequest) -> LipSyncResult:
        return LipSyncResult(
            status=LipSyncStatus.UNCONFIGURED,
            segment_id=request.segment_id,
            error_code=LipSyncErrorCode.MODEL_UNAVAILABLE,
            error_detail=f"provider {self.name!r} 未配置真实 GPU LipSync 引擎/权重",
        )

    def health_check(self) -> LipSyncResult:
        return LipSyncResult(
            status=LipSyncStatus.UNCONFIGURED, segment_id="",
            error_code=LipSyncErrorCode.MODEL_UNAVAILABLE,
        )


_DEFAULT_QA = LipSyncQAReport(
    boundary_score=0.92, skin_tone_score=0.9,
    motion_score=0.88, identity_score=0.95, passed=True,
)


class FakeLipSyncProvider:
    """确定性 Fake：不做真实口型（**零 GPU/模型/subprocess 导入**，AST 可验）。

    - `fail=True` → 模拟合成失败：FAILED + SYNTHESIS_FAILED，无产物无 QA。
    - 否则 → OK + dummy artifact id + 注入的 `qa`（默认通过）。**QA 可注入 passed=False**
      来驱动 domain 的"合成成功但 QA 不过 → 自动降级"路径测试——Fake 不自行降级
      （降级是 domain 的职责）。
    - deep-copy 输入；warnings 明示非真实口型。
    """

    def __init__(self, *, name: str = "lipsync.fake",
                  qa: LipSyncQAReport | None = None,
                  fail: bool = False) -> None:
        self.name = name
        self.qa = qa if qa is not None else _DEFAULT_QA
        self.fail = fail

    def synthesize(self, request: LipSyncRequest) -> LipSyncResult:
        req = deepcopy(request)
        if self.fail:
            return LipSyncResult(
                status=LipSyncStatus.FAILED, segment_id=req.segment_id,
                error_code=LipSyncErrorCode.SYNTHESIS_FAILED,
                error_detail="Fake 模拟合成失败",
                warnings=["Fake LipSync：模拟失败路径"],
            )
        return LipSyncResult(
            status=LipSyncStatus.OK, segment_id=req.segment_id,
            synthesized_artifact_id=f"fake-lipsync-{req.segment_id}",
            qa=self.qa,
            warnings=["Fake LipSync：非真实口型合成，仅供 pipeline 开发"],
        )

    def health_check(self) -> LipSyncResult:
        return LipSyncResult(status=LipSyncStatus.OK, segment_id="")


__all__ = [
    "FakeLipSyncProvider",
    "LipSyncErrorCode",
    "LipSyncProvider",
    "LipSyncRequest",
    "LipSyncResult",
    "LipSyncStatus",
    "UnconfiguredLipSyncProvider",
]
