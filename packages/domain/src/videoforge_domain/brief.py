"""从 Blueprint 抽 ClaimTable + 组装 CreativeBrief + 校验护栏（docs/modules/42 §2/§3.2）。纯函数。

- build_claim_table：VideoBlueprint.claims → ClaimTable，携事实状态/证据/置信；按文本去重；
  DISPUTED 事实 usable_in_rewrite=False（须人工核实），其余可用。新增/生成事实默认 UNVERIFIED，
  发布前不能自动通过（§2）。
- build_creative_brief：Opportunity + 创意参数（角度/受众/时长预算…）→ CreativeBrief，
  按 creation_mode 给默认 visual_mix。id/created_at 由调用方传入（不取时钟）。
- validate_brief：护栏——must_cover_claim_ids 引用真实 ClaimTable 条目、不得覆盖 DISPUTED 或
  不可用事实。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    ClaimSourceStatus,
    ClaimTable,
    ClaimTableEntry,
    CreationMode,
    CreativeBrief,
    CreativeOpportunity,
    VideoBlueprint,
    VisualMix,
)
from videoforge_contracts.brief import BriefHook

# 各创作模式的默认视觉配比（docs/modules/42 §2）
_DEFAULT_VISUAL_MIX: dict[CreationMode, VisualMix] = {
    CreationMode.STRUCTURE_REWRITE: VisualMix(
        talking_head=0.25, screen_demo=0.35, broll=0.2, info_card=0.2
    ),
    CreationMode.SOURCE_REEDIT: VisualMix(
        talking_head=0.15, screen_demo=0.45, broll=0.25, info_card=0.15
    ),
}


def build_claim_table(
    blueprint: VideoBlueprint, *, table_id: str, created_at: datetime
) -> ClaimTable:
    """VideoBlueprint 的 claims → ClaimTable（携事实状态/证据/置信），按文本去重。"""
    seen: set[str] = set()
    entries: list[ClaimTableEntry] = []
    for c in blueprint.claims:
        if c.text in seen:
            continue  # 同文本事实去重
        seen.add(c.text)
        entries.append(
            ClaimTableEntry(
                claim_id=c.id,
                text=c.text,
                fact_status=c.source_status,
                evidence=list(c.evidence),
                # DISPUTED 事实须人工核实，不可直接改写；新增/生成事实默认 UNVERIFIED 但可用于草稿
                usable_in_rewrite=c.source_status != ClaimSourceStatus.DISPUTED,
            )
        )
    return ClaimTable(
        id=table_id,
        source_blueprint_id=blueprint.id,
        entries=entries,
        created_at=created_at,
    )


def build_creative_brief(
    opportunity: CreativeOpportunity,
    *,
    brief_id: str,
    created_at: datetime,
    objective: str,
    audience: str,
    angle: str,
    duration_target_ms: int,
    creation_mode: CreationMode,
    claim_table: ClaimTable | None = None,
    platform: str | None = None,
    target_language: str | None = None,
    hook: BriefHook | None = None,
    must_cover_claim_ids: tuple[str, ...] = (),
    avoid: tuple[str, ...] = (),
    visual_mix: VisualMix | None = None,
    cta: str | None = None,
) -> CreativeBrief:
    """Opportunity + 创意参数 → CreativeBrief。visual_mix 缺省按 creation_mode 取默认。"""
    return CreativeBrief(
        id=brief_id,
        opportunity_id=opportunity.id,
        blueprint_id=opportunity.blueprint_id,
        claim_table_id=claim_table.id if claim_table is not None else None,
        objective=objective,
        audience=audience,
        platform=platform or opportunity.target_platform,
        target_language=target_language or opportunity.target_language,
        duration_target_ms=duration_target_ms,
        creation_mode=creation_mode,
        angle=angle,
        hook=hook,
        must_cover_claim_ids=list(must_cover_claim_ids),
        avoid=list(avoid),
        visual_mix=visual_mix or _DEFAULT_VISUAL_MIX.get(creation_mode),
        cta=cta,
        created_at=created_at,
    )


class BriefIssueKind(StrEnum):
    MUST_COVER_CLAIM_MISSING = "MUST_COVER_CLAIM_MISSING"
    MUST_COVER_CLAIM_DISPUTED = "MUST_COVER_CLAIM_DISPUTED"
    MUST_COVER_CLAIM_NOT_USABLE = "MUST_COVER_CLAIM_NOT_USABLE"


@dataclass(frozen=True)
class BriefIssue:
    kind: BriefIssueKind
    ref: str
    detail: str


def validate_brief(brief: CreativeBrief, claim_table: ClaimTable) -> list[BriefIssue]:
    """护栏：must_cover 的 Claim 必须在 ClaimTable 中、非 DISPUTED、可用于改写。"""
    entries = {e.claim_id: e for e in claim_table.entries}
    issues: list[BriefIssue] = []
    for cid in brief.must_cover_claim_ids:
        entry = entries.get(cid)
        if entry is None:
            issues.append(
                BriefIssue(BriefIssueKind.MUST_COVER_CLAIM_MISSING, cid, "不在 ClaimTable")
            )
            continue
        if entry.fact_status == ClaimSourceStatus.DISPUTED:
            issues.append(
                BriefIssue(BriefIssueKind.MUST_COVER_CLAIM_DISPUTED, cid, "有争议事实不得强制覆盖")
            )
        if not entry.usable_in_rewrite:
            issues.append(
                BriefIssue(BriefIssueKind.MUST_COVER_CLAIM_NOT_USABLE, cid, "标记为不可直接改写")
            )
    return issues


def is_valid_brief(brief: CreativeBrief, claim_table: ClaimTable) -> bool:
    return not validate_brief(brief, claim_table)
