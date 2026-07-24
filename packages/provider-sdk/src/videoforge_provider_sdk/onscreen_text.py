"""画面文字 Provider 端口 + Fake（docs/modules/43 §6.2）。

两个端口：
- `CleanPlateProvider`：从原视频估背景 / 授权 inpaint → 一段 Clean Plate 媒体产物。
- `TextRedrawProvider`：把目标语言文案渲染上 Clean Plate（含布局测量、字号回退）。

真实实现（多帧背景估计 / 授权 inpainting / OpenCV 排字 / VLM 布局求解）需权重与
GPU/CV 堆栈，属**停止条件延后**：
- `Unconfigured*` 版本恒返 UNCONFIGURED，绝不"猜"。
- `Fake*` 版本零 I/O、无图像库依赖，用**dummy 引用**（artifact_id 只是 "fake-cp-<n>"）
  让 pipeline 可跑通，UI 会看见明确的"未落地"标签而非静默假成品。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import CleanPlateRequest, TextTrackLocalizationDecision

# —— Clean Plate ——


class CleanPlateStatus(StrEnum):
    OK = "OK"
    FAILED = "FAILED"
    UNCONFIGURED = "UNCONFIGURED"


class CleanPlateErrorCode(StrEnum):
    PIPELINE_UNAVAILABLE = "PIPELINE_UNAVAILABLE"
    LICENSE_UNCONFIRMED = "LICENSE_UNCONFIRMED"
    UNSUPPORTED_METHOD = "UNSUPPORTED_METHOD"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CleanPlateResult:
    status: CleanPlateStatus
    request_id: str
    clean_plate_artifact_id: str | None = None
    provider: str | None = None
    error_code: CleanPlateErrorCode | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class CleanPlateProvider(Protocol):
    name: str
    execution_location: str

    def generate(self, request: CleanPlateRequest) -> CleanPlateResult: ...

    def health_check(self) -> CleanPlateResult: ...


class UnconfiguredCleanPlateProvider:
    """诚实占位：没有 Clean Plate pipeline，绝不产出。"""

    def __init__(self, *, name: str = "cleanplate.unconfigured",
                  execution_location: str = "local") -> None:
        self.name = name
        self.execution_location = execution_location

    def generate(self, request: CleanPlateRequest) -> CleanPlateResult:
        return CleanPlateResult(
            status=CleanPlateStatus.UNCONFIGURED, request_id=request.id,
            provider=self.name,
            error_code=CleanPlateErrorCode.PIPELINE_UNAVAILABLE,
            error_detail=(
                f"provider {self.name!r} 未配置 Clean Plate pipeline "
                f"(method={request.method.value})"
            ),
        )

    def health_check(self) -> CleanPlateResult:
        return CleanPlateResult(
            status=CleanPlateStatus.UNCONFIGURED, request_id="",
            error_code=CleanPlateErrorCode.PIPELINE_UNAVAILABLE,
        )


class FakeCleanPlateProvider:
    """确定性 Fake：不做真实图像操作；返回 dummy artifact id 让 pipeline 可跑通。

    - AUTHORIZED_INPAINT 无 license_ref 已经在合同层拦截；provider 侧对 SKIP method 返 OK
      但 warnings 明示 "no plate produced"（让 UI 显式看到）。
    - deep-copy request 输入，无内部状态。
    """

    def __init__(self, *, name: str = "cleanplate.fake",
                  execution_location: str = "local") -> None:
        self.name = name
        self.execution_location = execution_location
        self._counter = 0

    def generate(self, request: CleanPlateRequest) -> CleanPlateResult:
        req = deepcopy(request)
        from videoforge_contracts import CleanPlateMethod
        if req.method is CleanPlateMethod.SKIP:
            return CleanPlateResult(
                status=CleanPlateStatus.OK, request_id=req.id,
                clean_plate_artifact_id=None, provider=self.name,
                warnings=["SKIP method 未产出 Clean Plate（预期，如 REPLACE_OVERLAY 使用）"],
            )
        self._counter += 1
        return CleanPlateResult(
            status=CleanPlateStatus.OK, request_id=req.id,
            clean_plate_artifact_id=f"fake-cp-{req.id}-{self._counter}",
            provider=self.name,
            warnings=["Fake Clean Plate：非真实图像，仅供下游 pipeline 开发"],
        )

    def health_check(self) -> CleanPlateResult:
        return CleanPlateResult(status=CleanPlateStatus.OK, request_id="")


# —— Text Redraw ——


class TextRedrawStatus(StrEnum):
    OK = "OK"
    LAYOUT_OVERFLOW = "LAYOUT_OVERFLOW"  # 布局测量超模板容许，回退给上层
    FAILED = "FAILED"
    UNCONFIGURED = "UNCONFIGURED"


class TextRedrawErrorCode(StrEnum):
    RENDERER_UNAVAILABLE = "RENDERER_UNAVAILABLE"
    FONT_MISSING = "FONT_MISSING"
    CLEAN_PLATE_MISSING = "CLEAN_PLATE_MISSING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TextRedrawRequest:
    """一次重绘请求：decision + clean_plate_artifact_id。"""

    decision: TextTrackLocalizationDecision
    clean_plate_artifact_id: str | None = None
    max_expansion_ratio: float = 1.3


@dataclass(frozen=True)
class TextRedrawResult:
    status: TextRedrawStatus
    decision_ref: str
    rendered_artifact_id: str | None = None
    provider: str | None = None
    expansion_ratio: float | None = None
    error_code: TextRedrawErrorCode | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class TextRedrawProvider(Protocol):
    name: str
    execution_location: str

    def redraw(self, request: TextRedrawRequest) -> TextRedrawResult: ...

    def health_check(self) -> TextRedrawResult: ...


class UnconfiguredTextRedrawProvider:
    def __init__(self, *, name: str = "textredraw.unconfigured",
                  execution_location: str = "local") -> None:
        self.name = name
        self.execution_location = execution_location

    def redraw(self, request: TextRedrawRequest) -> TextRedrawResult:
        return TextRedrawResult(
            status=TextRedrawStatus.UNCONFIGURED,
            decision_ref=request.decision.source_track_id, provider=self.name,
            error_code=TextRedrawErrorCode.RENDERER_UNAVAILABLE,
            error_detail=f"provider {self.name!r} 未配置真实文字重绘",
        )

    def health_check(self) -> TextRedrawResult:
        return TextRedrawResult(
            status=TextRedrawStatus.UNCONFIGURED, decision_ref="",
            error_code=TextRedrawErrorCode.RENDERER_UNAVAILABLE,
        )


class FakeTextRedrawProvider:
    """确定性 Fake：按翻译文本长度估算 expansion_ratio；超阈值返回 LAYOUT_OVERFLOW；
    否则返回 dummy artifact id。零真实排字。

    - REDRAW 必须有 clean_plate；缺失 → FAILED + CLEAN_PLATE_MISSING。
    - deep-copy 输入。
    """

    def __init__(self, *, name: str = "textredraw.fake",
                  execution_location: str = "local") -> None:
        self.name = name
        self.execution_location = execution_location

    def redraw(self, request: TextRedrawRequest) -> TextRedrawResult:
        req = deepcopy(request)
        decision = req.decision
        if not decision.translated_text:
            return TextRedrawResult(
                status=TextRedrawStatus.FAILED,
                decision_ref=decision.source_track_id, provider=self.name,
                error_code=TextRedrawErrorCode.UNKNOWN,
                error_detail="decision.translated_text 为空，无法重绘",
            )
        if not req.clean_plate_artifact_id:
            return TextRedrawResult(
                status=TextRedrawStatus.FAILED,
                decision_ref=decision.source_track_id, provider=self.name,
                error_code=TextRedrawErrorCode.CLEAN_PLATE_MISSING,
                error_detail="REDRAW 缺 clean_plate_artifact_id",
            )
        src_len = max(1, len(decision.source_text))
        ratio = len(decision.translated_text) / src_len
        if ratio > req.max_expansion_ratio:
            return TextRedrawResult(
                status=TextRedrawStatus.LAYOUT_OVERFLOW,
                decision_ref=decision.source_track_id, provider=self.name,
                expansion_ratio=ratio,
                error_detail=(
                    f"目标语言扩张 {ratio:.2f}× 超阈值 {req.max_expansion_ratio:.2f}"
                ),
            )
        return TextRedrawResult(
            status=TextRedrawStatus.OK,
            decision_ref=decision.source_track_id, provider=self.name,
            rendered_artifact_id=f"fake-redraw-{decision.source_track_id}",
            expansion_ratio=ratio,
            warnings=["Fake 排字：非真实字体/布局，仅供 pipeline 开发"],
        )

    def health_check(self) -> TextRedrawResult:
        return TextRedrawResult(
            status=TextRedrawStatus.OK, decision_ref="",
        )


__all__ = [
    "CleanPlateErrorCode",
    "CleanPlateProvider",
    "CleanPlateResult",
    "CleanPlateStatus",
    "FakeCleanPlateProvider",
    "FakeTextRedrawProvider",
    "TextRedrawErrorCode",
    "TextRedrawProvider",
    "TextRedrawRequest",
    "TextRedrawResult",
    "TextRedrawStatus",
    "UnconfiguredCleanPlateProvider",
    "UnconfiguredTextRedrawProvider",
]
