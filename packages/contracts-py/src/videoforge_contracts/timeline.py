"""CreativeTimeline 合同（docs/modules/42 §8，ADR-003）。

ADR-003：CreativeTimeline 是**领域真值**，包含语义角色/模板槽位/字幕/来源等扩展字段；OTIO 只做
交换，Render Graph 交给渲染器。OTIO 不保存媒体、不覆盖所有高级动效，不可替代 CreativeTimeline。

Segment 除时间范围外承载九扩展字段（§8.2）：source_ref/semantic_role/script_sentence_id/
speaker_id/provenance_ref/template_slot/effects/crop_path/localization_policy——用于把回到源
（source→transcript→script）、模板套（brief→beat）、可溯性（provenance）、多语言（localization）
串成一条完整线索，OTIO 落 metadata.videoforge 保持不丢失。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import TrackKind


class RationalTime(ContractModel):
    """有理时间（OTIO 兼容）：value/rate 秒。等价性以 value*other.rate == other.value*rate 判定。"""

    value: int = Field(ge=0, description="以 rate 为单位的整数计数")
    rate: int = Field(gt=0, description="每秒计数，须与 timeline 一致")


class RationalTimeRange(ContractModel):
    """有理时间段 [start, start+duration)。duration 可为 0，表示瞬时点。"""

    start: RationalTime
    duration: RationalTime

    @model_validator(mode="after")
    def _same_rate(self) -> "RationalTimeRange":
        if self.start.rate != self.duration.rate:
            raise ValueError(
                f"RationalTimeRange start.rate({self.start.rate}) != "
                f"duration.rate({self.duration.rate})"
            )
        return self


class SegmentEffect(ContractModel):
    """效果占位：具体参数由 Render Graph 阶段消费；此处仅记录 kind + 参数字典。"""

    kind: str = Field(min_length=1)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)


class LocalizationPolicy(ContractModel):
    """本地化策略（多语言版本），标记本 Segment 依赖的语言资源。"""

    language: str = Field(min_length=1)
    strategy: str = Field(default="passthrough", description="passthrough/dub/subtitle_only …")


class Segment(ContractModel):
    """时间线上的一个片段（docs/modules/42 §8.2）。九扩展字段用于回溯语义、模板、来源、多语言。"""

    id: str = Field(min_length=1)
    time_range: RationalTimeRange
    source_ref: str | None = Field(default=None, description="源素材 asset_id 或占位")
    semantic_role: str | None = Field(default=None, description="如 HOOK/EVIDENCE/CTA")
    script_sentence_id: str | None = None
    speaker_id: str | None = None
    provenance_ref: str | None = Field(
        default=None, description="ResolvedAsset.id / Claim.id 等可溯性引用"
    )
    template_slot: str | None = None
    effects: list[SegmentEffect] = Field(default_factory=list)
    crop_path: str | None = Field(default=None, description="智能重构图的裁剪轨迹标识")
    localization: LocalizationPolicy | None = None


class Track(ContractModel):
    """时间线单轨（docs/modules/42 §8.1）。同轨 segment 不得重叠，由 validate_timeline 检查。"""

    id: str = Field(min_length=1)
    kind: TrackKind
    segments: list[Segment] = Field(default_factory=list)


class CreativeTimeline(ContractModel):
    """领域时间线真值（ADR-003）：rate + 多轨 + 总时长 + 来源引用。"""

    id: str = Field(min_length=1)
    project_id: str | None = None
    rate: int = Field(gt=0, description="全 timeline 帧率/采样率基准；所有 track/segment 须一致")
    duration: RationalTime
    tracks: list[Track] = Field(default_factory=list)
    source_transcript_id: str | None = None
    source_asset_ids: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def _duration_rate_matches(self) -> "CreativeTimeline":
        if self.duration.rate != self.rate:
            raise ValueError(
                f"CreativeTimeline duration.rate({self.duration.rate}) != rate({self.rate})"
            )
        return self
