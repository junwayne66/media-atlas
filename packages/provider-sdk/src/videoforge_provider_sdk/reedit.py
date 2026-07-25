"""句段重剪判定端口 + Fake（docs/modules/42 §4.1）。

"哪些句段该删（静音/口头禅/重复/低信息）"本质是模型判断——真实实现需 ASR 文本分析/VLM 或训练
模型（停止条件延后）。默认 UnconfiguredSegmentJudgeProvider 诚实返回 UNCONFIGURED；Fake 按文本/时长
确定性判定（空→静音、口头禅词→filler、与上句重复→repeat），供下游 build_reedit_plan 消费。

计划生成/连续性/不切句/变速护栏属纯域（domain.build_reedit_plan / validate_reedit_plan），故本端口
contracts-only、不依赖 domain。每次都新建 SegmentJudgment，无录制、无共享可变态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import SegmentJudgment

# 常见口头禅/语气词（中英），命中即判 filler
_FILLER_WORDS = frozenset(
    {"嗯", "呃", "啊", "那个", "这个", "就是", "然后", "um", "uh", "er", "like", "you know"}
)


class SegmentJudgeStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"


class SegmentJudgeErrorCode(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class SegmentSpec:
    """待判定的源句段（provider 侧最小视图）。"""

    id: str
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True)
class SegmentJudgeRequest:
    segments: list[SegmentSpec]


@dataclass
class SegmentJudgeResult:
    status: SegmentJudgeStatus
    provider: str
    judgments: list[SegmentJudgment] = field(default_factory=list)  # 与 request.segments 对齐
    error_code: SegmentJudgeErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == SegmentJudgeStatus.OK


@runtime_checkable
class SegmentJudgeProvider(Protocol):
    name: str
    execution_location: str

    def judge(self, request: SegmentJudgeRequest) -> SegmentJudgeResult:
        """为每个源句段判定是否保留（与 request.segments 顺序对齐）。"""
        ...

    def health_check(self) -> SegmentJudgeResult: ...


class UnconfiguredSegmentJudgeProvider:
    """默认：真实句段判定模型未接入。返回 UNCONFIGURED，不静默假装。"""

    def __init__(
        self, name: str = "segjudge.unconfigured", *, execution_location: str = "cloud"
    ) -> None:
        self.name = name
        self.execution_location = execution_location

    def judge(self, request: SegmentJudgeRequest) -> SegmentJudgeResult:
        return SegmentJudgeResult(
            status=SegmentJudgeStatus.UNCONFIGURED,
            provider=self.name,
            error_code=SegmentJudgeErrorCode.UNCONFIGURED,
            detail="句段重剪判定模型未接入（需文本分析/VLM 或训练模型）；请人工标注或稍后重试",
        )

    def health_check(self) -> SegmentJudgeResult:
        return SegmentJudgeResult(status=SegmentJudgeStatus.UNCONFIGURED, provider=self.name)


class FakeSegmentJudgeProvider:
    """确定性 Fake：空文本→静音、口头禅词→filler、与上一保留句相同→repeat，其余保留。供下游开发。"""

    def __init__(self, *, name: str = "segjudge.fake", execution_location: str = "cloud") -> None:
        self.name = name
        self.execution_location = execution_location

    def judge(self, request: SegmentJudgeRequest) -> SegmentJudgeResult:
        judgments: list[SegmentJudgment] = []
        prev_kept_text: str | None = None
        for seg in request.segments:
            norm = seg.text.strip()
            if not norm:
                judgments.append(
                    SegmentJudgment(segment_id=seg.id, keep_recommended=False, is_silence=True)
                )
                continue
            if norm.lower() in _FILLER_WORDS:
                judgments.append(
                    SegmentJudgment(segment_id=seg.id, keep_recommended=False, is_filler=True)
                )
                continue
            if prev_kept_text is not None and norm == prev_kept_text:
                judgments.append(
                    SegmentJudgment(segment_id=seg.id, keep_recommended=False, is_repeat=True)
                )
                continue
            judgments.append(SegmentJudgment(segment_id=seg.id, keep_recommended=True))
            prev_kept_text = norm
        return SegmentJudgeResult(
            status=SegmentJudgeStatus.OK, provider=self.name, judgments=judgments
        )

    def health_check(self) -> SegmentJudgeResult:
        return SegmentJudgeResult(status=SegmentJudgeStatus.OK, provider=self.name)


__all__ = [
    "FakeSegmentJudgeProvider",
    "SegmentJudgeErrorCode",
    "SegmentJudgeProvider",
    "SegmentJudgeRequest",
    "SegmentJudgeResult",
    "SegmentJudgeStatus",
    "SegmentSpec",
    "UnconfiguredSegmentJudgeProvider",
]
