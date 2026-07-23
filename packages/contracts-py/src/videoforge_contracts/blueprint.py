"""VideoBlueprint 合同（docs/modules/41 §10）。事实层（claims）与表达层（beats）分开。

融合 ASR/OCR/VLM 而成：claims 是可核验陈述且必须引用 transcript/OCR 的证据 span；
rhetorical_beats 是钩子/证据/CTA 等抽象节拍；visual_beats 是人物/屏录/产品等画面功能。
后续结构重写只消费抽象节拍 + 经核验 claims，绝不把完整转录当改写提示词（§10.1）。

时间戳不由 LLM 编造——时间范围由程序从段落/场景提供候选，且经 domain.validate_blueprint
校验单调、在时长内、证据引用真实（§10.2）。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import (
    ClaimSourceStatus,
    RhetoricalBeatKind,
    VisualBeatKind,
)


class EvidenceSpan(ContractModel):
    """Claim 的证据来源：引用 transcript 段或 OCR 文本轨的时间片。"""

    kind: str = Field(pattern=r"^(transcript|ocr)$", description="证据来源类型")
    ref_id: str = Field(min_length=1, description="被引 transcript 段 id 或 TextTrack id")
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_span(self) -> "EvidenceSpan":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        return self


class Claim(ContractModel):
    """可核验陈述（事实层）。必须至少引用一条证据 span（§10.2）。"""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)
    source_status: ClaimSourceStatus = ClaimSourceStatus.UNVERIFIED
    evidence: list[EvidenceSpan] = Field(min_length=1, description="至少一条证据，禁凭空 Claim")


class RhetoricalBeat(ContractModel):
    """表达层节拍。时间范围由程序候选，kind 由融合分类。"""

    id: str = Field(min_length=1)
    kind: RhetoricalBeatKind
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    summary: str | None = None
    claim_ids: list[str] = Field(default_factory=list, description="本节拍提出的 Claim id")

    @model_validator(mode="after")
    def _check_span(self) -> "RhetoricalBeat":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        return self


class VisualBeat(ContractModel):
    """视觉层节拍（画面功能）。"""

    id: str = Field(min_length=1)
    kind: VisualBeatKind
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    frame_time_ms: int | None = Field(default=None, ge=0, description="代表帧时间")

    @model_validator(mode="after")
    def _check_span(self) -> "VisualBeat":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        return self


class VideoBlueprint(ContractModel):
    """视频蓝图：事实层 + 表达层 + 视觉层（§10）。经 validate_blueprint 强校验后方可下游消费。"""

    id: str = Field(min_length=1)
    source_artifact_id: str | None = None
    duration_ms: int = Field(gt=0)
    claims: list[Claim] = Field(default_factory=list)
    rhetorical_beats: list[RhetoricalBeat] = Field(default_factory=list)
    visual_beats: list[VisualBeat] = Field(default_factory=list)
    coverage: float | None = Field(
        default=None, ge=0.0, le=1.0, description="rhetorical 节拍时间覆盖率（§10.2 目标 ≥0.9）"
    )
    fusion_provider: str | None = None
    created_at: datetime
