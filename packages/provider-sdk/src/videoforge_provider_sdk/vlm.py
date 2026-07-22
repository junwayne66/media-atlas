"""VLM 端口 + Fake（docs/modules/41 §9）。

VLM 只分析代表帧集，**批量一次调用**（analyze 接整个 VisualAnalysis 的选中帧），从端口
形状上杜绝逐帧云调用（成本红线）。真实引擎（Qwen-VL / Claude 等 API 或本地 VLM）需模型/
授权，属停止条件延后：默认 UnconfiguredVLMProvider 诚实返回 UNCONFIGURED；FakeVLMProvider
按 frame_time 回放录制 caption/labels。

缓存：同一批帧的分析由上层用 VF-201 的 activity_cache_key 去重，命中不重复调用（41 §11）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import VisualAnalysis


class VLMStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"  # 真实引擎未接入（需模型/授权，停止条件）


class VLMErrorCode(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class VLMRequest:
    analysis: VisualAnalysis  # 待分析的代表帧集（caption 未填）——整批传入，一次调用
    prompt: str = "描述画面内容并标注对象（人物/屏录/产品/图卡等）"


@dataclass
class VLMResult:
    status: VLMStatus
    provider: str
    analysis: VisualAnalysis | None = None  # 回填 caption/labels 后的分析
    error_code: VLMErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == VLMStatus.OK


@runtime_checkable
class VLMProvider(Protocol):
    name: str
    execution_location: str

    def analyze(self, request: VLMRequest) -> VLMResult:
        """批量分析整批代表帧（禁逐帧）；回填 caption/labels 后返回新 VisualAnalysis。"""
        ...

    def health_check(self) -> VLMResult: ...


class UnconfiguredVLMProvider:
    """默认：真实引擎未接入（需模型/授权）。返回 UNCONFIGURED，不静默假装。"""

    def __init__(
        self, name: str = "vlm.unconfigured", *, execution_location: str = "cloud"
    ) -> None:
        self.name = name
        self.execution_location = execution_location

    def analyze(self, request: VLMRequest) -> VLMResult:
        return VLMResult(
            status=VLMStatus.UNCONFIGURED,
            provider=self.name,
            error_code=VLMErrorCode.UNCONFIGURED,
            detail="VLM 未接入（需模型/授权）；请人工标注或稍后重试",
        )

    def health_check(self) -> VLMResult:
        return VLMResult(status=VLMStatus.UNCONFIGURED, provider=self.name)


# 录制 caption：frame_time_ms → (caption, labels, confidence)
FrameCaption = tuple[str, list[str], float]


class FakeVLMProvider:
    """回放录制 caption/labels，一次批量处理整帧集（call_count 记录调用次数以证批量）。"""

    def __init__(
        self,
        *,
        name: str,
        captions: dict[int, FrameCaption],
        version: str = "fake",
        execution_location: str = "cloud",
    ) -> None:
        self.name = name
        # 入参侧也隔离：拷贝每条录制的 labels 列表，调用方事后改自己的 dict 不影响回放
        self._captions = {k: (c, list(labels), conf) for k, (c, labels, conf) in captions.items()}
        self.version = version
        self.execution_location = execution_location
        self.call_count = 0

    def analyze(self, request: VLMRequest) -> VLMResult:
        self.call_count += 1  # 整批一次调用——绝不逐帧
        filled = []
        for f in request.analysis.frames:
            rec = self._captions.get(f.frame_time_ms)
            if rec is None:
                filled.append(f.model_copy(deep=True))  # 无录制则留 caption=None（诚实）
                continue
            caption, labels, conf = rec
            filled.append(
                f.model_copy(
                    update={"caption": caption, "labels": list(labels), "confidence": conf},
                    deep=True,
                )
            )
        analysis = request.analysis.model_copy(
            update={
                "frames": filled,
                "vlm_provider": self.name,
                "vlm_version": self.version,
            }
        )
        return VLMResult(status=VLMStatus.OK, provider=self.name, analysis=analysis)

    def health_check(self) -> VLMResult:
        return VLMResult(status=VLMStatus.OK, provider=self.name)


__all__ = [
    "FakeVLMProvider",
    "FrameCaption",
    "UnconfiguredVLMProvider",
    "VLMErrorCode",
    "VLMProvider",
    "VLMRequest",
    "VLMResult",
    "VLMStatus",
]
