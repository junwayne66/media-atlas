"""结构重写端口 + Fake（docs/modules/42 §3）。

真实改写引擎（LLM）在 BeatTemplate + ClaimTable 上生成中性语义脚本——只依据节拍功能与
经核验事实，绝不复用原句。需模型/授权，属停止条件延后：默认 UnconfiguredStructureRewriteProvider
诚实返回 UNCONFIGURED；FakeStructureRewriteProvider 按模板生成不抄源、引真实 Claim、
总时长=预算的合法 ScriptVersion（供 domain.validate_script 验证通过）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import (
    BeatTemplate,
    ClaimSourceStatus,
    ClaimTable,
    CreativeBrief,
    RhetoricalBeatKind,
    ScriptSentence,
    ScriptVersion,
    Transcript,
)

# 每个节拍角色的中性模板文案（刻意与任何真实转录不同，避免抄袭；真实引擎由 LLM 生成）
_ROLE_TEMPLATE_ZH: dict[RhetoricalBeatKind, str] = {
    RhetoricalBeatKind.HOOK: "用一个反常识切入点带出本段主题",
    RhetoricalBeatKind.QUESTION: "抛出观众关心的核心疑问",
    RhetoricalBeatKind.EVIDENCE: "依据核验要点摆出实测与数据支撑",
    RhetoricalBeatKind.CONTRAST: "对照说明其中的差异与取舍",
    RhetoricalBeatKind.DEMO: "以演示方式呈现关键操作",
    RhetoricalBeatKind.CONCLUSION: "归纳本段结论并点明适用人群",
    RhetoricalBeatKind.CTA: "引导观众留言互动",
    RhetoricalBeatKind.UNCLASSIFIED: "承接上下文补充说明",
}
_ROLE_TEMPLATE_EN: dict[RhetoricalBeatKind, str] = {
    RhetoricalBeatKind.HOOK: "open with a counter-intuitive angle for this beat",
    RhetoricalBeatKind.QUESTION: "raise the core question the audience cares about",
    RhetoricalBeatKind.EVIDENCE: "lay out the measured evidence per verified points",
    RhetoricalBeatKind.CONTRAST: "contrast the trade-offs involved",
    RhetoricalBeatKind.DEMO: "present the key steps as a demonstration",
    RhetoricalBeatKind.CONCLUSION: "summarize the takeaway and who it fits",
    RhetoricalBeatKind.CTA: "invite the audience to comment",
    RhetoricalBeatKind.UNCLASSIFIED: "bridge and add supporting context",
}


class RewriteStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    UNCONFIGURED = "unconfigured"


class RewriteErrorCode(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class RewriteRequest:
    script_id: str
    created_at: datetime
    language: str
    beat_template: BeatTemplate
    claim_table: ClaimTable
    brief: CreativeBrief | None = None
    source_transcript: Transcript | None = None  # 真实引擎用于避抄；Fake 用模板天然避抄


@dataclass
class RewriteResult:
    status: RewriteStatus
    provider: str
    script: ScriptVersion | None = None
    error_code: RewriteErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == RewriteStatus.OK


@runtime_checkable
class StructureRewriteProvider(Protocol):
    name: str
    execution_location: str

    def rewrite(self, request: RewriteRequest) -> RewriteResult:
        """在 BeatTemplate + ClaimTable 上生成中性语义脚本（不抄源、引经核验事实）。"""
        ...

    def health_check(self) -> RewriteResult: ...


class UnconfiguredStructureRewriteProvider:
    """默认：真实改写 LLM 未接入。返回 UNCONFIGURED，不静默假装。"""

    def __init__(self, name: str = "rewrite.unconfigured", *, execution_location: str = "cloud"):
        self.name = name
        self.execution_location = execution_location

    def rewrite(self, request: RewriteRequest) -> RewriteResult:
        return RewriteResult(
            status=RewriteStatus.UNCONFIGURED,
            provider=self.name,
            error_code=RewriteErrorCode.UNCONFIGURED,
            detail="结构重写 LLM 未接入（需模型/授权）；请人工撰写或稍后重试",
        )

    def health_check(self) -> RewriteResult:
        return RewriteResult(status=RewriteStatus.UNCONFIGURED, provider=self.name)


class FakeStructureRewriteProvider:
    """确定性 Fake：按模板逐槽生成不抄源的中性句，把可用 must_cover 事实挂到最长节拍上。"""

    def __init__(self, *, name: str = "rewrite.fake", execution_location: str = "cloud") -> None:
        self.name = name
        self.execution_location = execution_location

    def rewrite(self, request: RewriteRequest) -> RewriteResult:
        lang = request.language
        table = {e.claim_id for e in request.claim_table.entries}
        usable = {
            e.claim_id
            for e in request.claim_table.entries
            if e.fact_status != ClaimSourceStatus.DISPUTED and e.usable_in_rewrite
        }
        must_cover = tuple(request.brief.must_cover_claim_ids) if request.brief else ()
        cite = [c for c in must_cover if c in table and c in usable]

        slots = request.beat_template.slots
        # 事实挂到时长最长的节拍（通常是主体/EVIDENCE）
        body_idx = (
            max(range(len(slots)), key=lambda i: slots[i].target_duration_ms) if slots else -1
        )
        templates = _ROLE_TEMPLATE_ZH if lang.lower().startswith("zh") else _ROLE_TEMPLATE_EN

        sentences: list[ScriptSentence] = []
        for i, slot in enumerate(slots):
            sentences.append(
                ScriptSentence(
                    id=f"s-{i}",
                    beat_slot_id=slot.id,
                    role=slot.role,
                    text=templates.get(slot.role, templates[RhetoricalBeatKind.UNCLASSIFIED]),
                    target_duration_ms=slot.target_duration_ms,  # 总和 = 模板总时长 = 预算
                    claim_ids=list(cite) if i == body_idx else [],
                    language=lang,
                )
            )
        script = ScriptVersion(
            id=request.script_id,
            brief_id=request.brief.id if request.brief else None,
            beat_template_id=request.beat_template.id,
            claim_table_id=request.claim_table.id,
            language=lang,
            sentences=sentences,
            total_duration_ms=sum(s.target_duration_ms for s in sentences),
            rewrite_provider=self.name,
            created_at=request.created_at,
        )
        return RewriteResult(status=RewriteStatus.OK, provider=self.name, script=script)

    def health_check(self) -> RewriteResult:
        return RewriteResult(status=RewriteStatus.OK, provider=self.name)


__all__ = [
    "FakeStructureRewriteProvider",
    "RewriteErrorCode",
    "RewriteRequest",
    "RewriteResult",
    "RewriteStatus",
    "StructureRewriteProvider",
    "UnconfiguredStructureRewriteProvider",
]
