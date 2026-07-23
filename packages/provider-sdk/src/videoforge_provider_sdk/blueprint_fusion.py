"""Blueprint 融合端口 + Fake（docs/modules/41 §10）。

融合 ASR/OCR/VLM → VideoBlueprint：时间范围由程序（domain.build_candidate_rhetorical_beats）
提供，Provider（LLM）只在候选节拍上改 kind、抽取引用真实证据的 Claim——绝不编造时间戳。
真实 LLM 需模型/授权，属停止条件延后：默认 UnconfiguredBlueprintFusionProvider 诚实返回
UNCONFIGURED；FakeBlueprintFusionProvider 用候选 + 简单启发式产出通过 domain.validate_blueprint
的合法蓝图（claim 引用真实转录段）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import (
    Claim,
    ClaimSourceStatus,
    EvidenceSpan,
    RhetoricalBeat,
    RhetoricalBeatKind,
    Transcript,
    VideoBlueprint,
    VisualBeat,
)


class BlueprintFusionStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"  # 真实 LLM 未接入（需模型/授权，停止条件）


class BlueprintFusionErrorCode(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    BLUEPRINT_SCHEMA_INVALID = "BLUEPRINT_SCHEMA_INVALID"  # §12
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class BlueprintFusionRequest:
    blueprint_id: str
    created_at: datetime
    duration_ms: int
    candidate_beats: list[RhetoricalBeat]  # 程序提供的候选（全 UNCLASSIFIED）
    visual_beats: list[VisualBeat] = field(default_factory=list)
    transcript: Transcript | None = None
    source_artifact_id: str | None = None


@dataclass
class BlueprintFusionResult:
    status: BlueprintFusionStatus
    provider: str
    blueprint: VideoBlueprint | None = None
    error_code: BlueprintFusionErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == BlueprintFusionStatus.OK


@runtime_checkable
class BlueprintFusionProvider(Protocol):
    name: str
    execution_location: str

    def fuse(self, request: BlueprintFusionRequest) -> BlueprintFusionResult:
        """在候选节拍上分类 + 抽 Claim → VideoBlueprint（时间戳不越候选）。"""
        ...

    def health_check(self) -> BlueprintFusionResult: ...


class UnconfiguredBlueprintFusionProvider:
    """默认：真实 LLM 融合未接入。返回 UNCONFIGURED，不静默假装。"""

    def __init__(self, name: str = "blueprint.unconfigured", *, execution_location: str = "cloud"):
        self.name = name
        self.execution_location = execution_location

    def fuse(self, request: BlueprintFusionRequest) -> BlueprintFusionResult:
        return BlueprintFusionResult(
            status=BlueprintFusionStatus.UNCONFIGURED,
            provider=self.name,
            error_code=BlueprintFusionErrorCode.UNCONFIGURED,
            detail="Blueprint 融合 LLM 未接入（需模型/授权）；请人工融合或稍后重试",
        )

    def health_check(self) -> BlueprintFusionResult:
        return BlueprintFusionResult(status=BlueprintFusionStatus.UNCONFIGURED, provider=self.name)


class FakeBlueprintFusionProvider:
    """确定性 Fake：候选首→HOOK、末→CTA、中间保持 UNCLASSIFIED（诚实：不假装分类）；
    从首个转录段抽一条 Claim 并引用该段为证据。产出通过 domain.validate_blueprint 的合法蓝图。"""

    def __init__(self, *, name: str = "blueprint.fake", execution_location: str = "cloud") -> None:
        self.name = name
        self.execution_location = execution_location

    def fuse(self, request: BlueprintFusionRequest) -> BlueprintFusionResult:
        cands = request.candidate_beats
        n = len(cands)
        beats: list[RhetoricalBeat] = []
        for i, cb in enumerate(cands):
            if i == 0 and n > 1:
                kind = RhetoricalBeatKind.HOOK
            elif i == n - 1 and n > 1:
                kind = RhetoricalBeatKind.CTA
            else:
                kind = RhetoricalBeatKind.UNCLASSIFIED
            beats.append(cb.model_copy(update={"kind": kind}, deep=True))

        claims: list[Claim] = []
        tr = request.transcript
        if tr is not None and tr.segments:
            seg = tr.segments[0]
            claims.append(
                Claim(
                    id="claim-0",
                    text=seg.text or "(无文本)",
                    source_status=ClaimSourceStatus.UNVERIFIED,
                    evidence=[
                        EvidenceSpan(
                            kind="transcript",
                            ref_id=seg.id,
                            start_ms=seg.start_ms,
                            end_ms=min(seg.end_ms, request.duration_ms),
                        )
                    ],
                )
            )
            # 把 claim 挂到覆盖该段起点的节拍上
            for idx, b in enumerate(beats):
                if b.start_ms <= seg.start_ms < b.end_ms:
                    beats[idx] = b.model_copy(update={"claim_ids": ["claim-0"]}, deep=True)
                    break

        blueprint = VideoBlueprint(
            id=request.blueprint_id,
            source_artifact_id=request.source_artifact_id,
            duration_ms=request.duration_ms,
            claims=claims,
            rhetorical_beats=beats,
            visual_beats=[vb.model_copy(deep=True) for vb in request.visual_beats],
            fusion_provider=self.name,
            created_at=request.created_at,
        )
        return BlueprintFusionResult(
            status=BlueprintFusionStatus.OK, provider=self.name, blueprint=blueprint
        )

    def health_check(self) -> BlueprintFusionResult:
        return BlueprintFusionResult(status=BlueprintFusionStatus.OK, provider=self.name)


__all__ = [
    "BlueprintFusionErrorCode",
    "BlueprintFusionProvider",
    "BlueprintFusionRequest",
    "BlueprintFusionResult",
    "BlueprintFusionStatus",
    "FakeBlueprintFusionProvider",
    "UnconfiguredBlueprintFusionProvider",
]
