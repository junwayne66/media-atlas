"""热门片段特征端口 + Fake（docs/modules/42 §5.2）。

11 项特征子分（hook_strength/surprise/emotional_energy…）本质是模型判断——真实实现需 VLM/LLM 或
训练模型（停止条件延后）。默认 UnconfiguredHighlightFeatureProvider 诚实返回 UNCONFIGURED；
FakeHighlightFeatureProvider 从窗口的结构性属性（位置/时长/文本）确定性推导特征，供下游开发。

评分聚合（highlight_score）+ 去重 + MMR 属纯域（domain.rank_highlights）——本端口只产特征，故
contracts-only、不依赖 domain。每次都新建 HighlightFeatures（无录制、无共享可变态），不泄漏引用。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import HighlightFeatures


class HighlightFeatureStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"


class HighlightFeatureErrorCode(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class HighlightWindowSpec:
    """待评特征的候选窗口（provider 侧最小视图，不依赖 domain 的 CandidateWindow）。"""

    start_ms: int
    end_ms: int
    text: str
    index_in_video: int = 0  # 第几个窗口（位置线索：越靠前 hook 越强）
    total_windows: int = 1

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True)
class HighlightFeatureRequest:
    windows: list[HighlightWindowSpec]
    video_duration_ms: int | None = None


@dataclass
class HighlightFeatureResult:
    status: HighlightFeatureStatus
    provider: str
    features: list[HighlightFeatures] = field(default_factory=list)  # 与 request.windows 对齐
    error_code: HighlightFeatureErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == HighlightFeatureStatus.OK


@runtime_checkable
class HighlightFeatureProvider(Protocol):
    name: str
    execution_location: str

    def score(self, request: HighlightFeatureRequest) -> HighlightFeatureResult:
        """为每个候选窗口产出 11 项特征子分（与 request.windows 顺序对齐）。"""
        ...

    def health_check(self) -> HighlightFeatureResult: ...


class UnconfiguredHighlightFeatureProvider:
    """默认：真实特征模型未接入。返回 UNCONFIGURED，不静默假装。"""

    def __init__(
        self, name: str = "highlight.unconfigured", *, execution_location: str = "cloud"
    ) -> None:
        self.name = name
        self.execution_location = execution_location

    def score(self, request: HighlightFeatureRequest) -> HighlightFeatureResult:
        return HighlightFeatureResult(
            status=HighlightFeatureStatus.UNCONFIGURED,
            provider=self.name,
            error_code=HighlightFeatureErrorCode.UNCONFIGURED,
            detail="热门片段特征模型未接入（需 VLM/LLM 或训练模型）；请人工挑选或稍后重试",
        )

    def health_check(self) -> HighlightFeatureResult:
        return HighlightFeatureResult(
            status=HighlightFeatureStatus.UNCONFIGURED, provider=self.name
        )


def _unit_hash(text: str, salt: str) -> float:
    """从文本确定性派生 [0,1]。仅供 Fake 给"主观"特征造可复现的展开，非真实判断。"""
    digest = hashlib.blake2b((salt + "\x00" + text).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(2**64 - 1)


class FakeHighlightFeatureProvider:
    """确定性 Fake：从窗口结构性属性 + 文本哈希推导 11 项特征（可复现、无随机）。仅供下游开发。"""

    def __init__(self, *, name: str = "highlight.fake", execution_location: str = "cloud") -> None:
        self.name = name
        self.execution_location = execution_location

    def _derive(self, w: HighlightWindowSpec, video_ms: int | None) -> HighlightFeatures:
        # 位置：越靠前 hook 越强，越靠后 ending_payoff 越强
        pos = w.index_in_video / (w.total_windows - 1) if w.total_windows > 1 else 0.0
        hook = round(max(0.0, 1.0 - 0.6 * pos), 4)
        ending = round(min(1.0, 0.4 + 0.5 * pos), 4)
        # 文本长度 → 信息密度（越长越密，200 字封顶）
        density = round(min(1.0, len(w.text) / 200.0), 4)
        # 时长甜区（约 25s）自足度最高，偏离衰减
        dur_s = w.duration_ms / 1000.0
        self_contained = round(max(0.0, 1.0 - abs(dur_s - 25.0) / 50.0), 4)
        # 上下文依赖：不从 0 开始的窗口需要前情，越靠后越依赖
        if video_ms and video_ms > 0:
            context_dep = round(min(0.9, w.start_ms / video_ms), 4)
        else:
            context_dep = 0.0 if w.start_ms == 0 else 0.3
        return HighlightFeatures(
            hook_strength=hook,
            self_containedness=self_contained,
            information_density=density,
            surprise_or_conflict=round(_unit_hash(w.text, "surprise"), 4),
            emotional_energy=round(_unit_hash(w.text, "emotional"), 4),
            topic_relevance=round(0.5 + 0.5 * _unit_hash(w.text, "topic"), 4),
            visual_activity=round(_unit_hash(w.text, "visual"), 4),
            speaker_prominence=round(_unit_hash(w.text, "speaker"), 4),
            ending_payoff=ending,
            context_dependency=context_dep,
            technical_defect=0.05,
        )

    def score(self, request: HighlightFeatureRequest) -> HighlightFeatureResult:
        feats = [self._derive(w, request.video_duration_ms) for w in request.windows]
        return HighlightFeatureResult(
            status=HighlightFeatureStatus.OK, provider=self.name, features=feats
        )

    def health_check(self) -> HighlightFeatureResult:
        return HighlightFeatureResult(status=HighlightFeatureStatus.OK, provider=self.name)


__all__ = [
    "FakeHighlightFeatureProvider",
    "HighlightFeatureErrorCode",
    "HighlightFeatureProvider",
    "HighlightFeatureRequest",
    "HighlightFeatureResult",
    "HighlightFeatureStatus",
    "HighlightWindowSpec",
    "UnconfiguredHighlightFeatureProvider",
]
