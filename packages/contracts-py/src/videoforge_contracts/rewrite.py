"""结构重写合同（docs/modules/42 §3）。

BeatTemplate：把参考 VideoBlueprint 抽象为「节拍功能 + 时长比例」，缩放到目标时长——
只复用节拍功能和时长比，绝不复用原句/原配音/特有画面/品牌表达（§3.1）。
ScriptVersion：中性语义脚本，逐句可编辑，每句带 target_duration_ms（按语速估算，非字符粗算）、
引用的 Claim。经 domain.validate_script 强校验（不抄源/事实/时长/禁用词）后方可下游消费。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import RhetoricalBeatKind


class BeatSlot(ContractModel):
    """节拍槽位：功能 + 目标时长（不含原句）。"""

    id: str = Field(min_length=1)
    role: RhetoricalBeatKind
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    target_duration_ms: int = Field(ge=0)
    guidance: str | None = Field(default=None, description="本节拍应达成的功能（抽象，非原句）")

    @model_validator(mode="after")
    def _check_span(self) -> "BeatSlot":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        return self


class BeatTemplate(ContractModel):
    """抽象节拍模板（缩放到目标时长）。只复用节拍功能 + 时长比。"""

    id: str = Field(min_length=1)
    source_blueprint_id: str | None = None
    duration_target_ms: int = Field(gt=0)
    slots: list[BeatSlot] = Field(default_factory=list)
    created_at: datetime


class ScriptSentence(ContractModel):
    """Canonical Script 的一句：中性语义、逐句可编辑，带估算时长与引用 Claim。"""

    id: str = Field(min_length=1)
    beat_slot_id: str = Field(min_length=1)
    role: RhetoricalBeatKind
    text: str = Field(min_length=1)
    target_duration_ms: int = Field(ge=0, description="按语言语速估算，非字符粗算")
    claim_ids: list[str] = Field(default_factory=list, description="本句主张的 Claim 引用")
    language: str = Field(min_length=1)
    editable: bool = True


class ScriptVersion(ContractModel):
    """可逐句编辑的脚本版本（docs/modules/42 §3.2 第 7 步）。"""

    id: str = Field(min_length=1)
    brief_id: str | None = None
    beat_template_id: str | None = None
    claim_table_id: str | None = None
    version: int = Field(default=1, ge=1)
    language: str = Field(min_length=1)
    sentences: list[ScriptSentence] = Field(default_factory=list)
    total_duration_ms: int | None = Field(default=None, ge=0)
    rewrite_provider: str | None = None
    created_at: datetime
