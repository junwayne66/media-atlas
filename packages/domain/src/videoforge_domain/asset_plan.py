"""素材规划解析（docs/modules/42 §6）。纯函数，可复现。

- match_score：§6.2 加权公式（语义/构图/分辨率/运动/颜色/品牌/复用惩罚），系数模板化，bit 复现。
- resolve_asset_plan：五级 Resolver 优先级——授权原片 → 自有库 → 商业/许可 → AI 生成 → 占位；
  每级按 match_score 排序取首个通过阈值、且被 slot 允许来源接受的候选；全级未命中走 fallback 占位。
- validate_asset_plan 护栏：每 ResolvedAsset 必带来源+许可+检索词+使用区间；来源必须落在
  slot.allowed_sources 内；使用区间落在 slot 时间范围内；复用不超过复用限。

真实素材源（自有库语义检索/商业 stock/AI 生成/数字人）属停止条件延后；本域只做评分+优先级+护栏。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    AssetLicense,
    AssetLicenseType,
    AssetPlan,
    AssetPlanSlot,
    AssetRole,
    AssetSource,
    ResolvedAsset,
)

# 五级 Resolver 顺序（docs/modules/42 §6.2）
RESOLVER_PRIORITY: tuple[AssetSource, ...] = (
    AssetSource.SOURCE,
    AssetSource.OWN_LIBRARY,
    AssetSource.STOCK,
    AssetSource.GENERATED,
    AssetSource.PLACEHOLDER,
)

_MATCH_ACCEPT_THRESHOLD = 0.5  # 分数低于此不算合格候选
_REUSE_PENALTY_PER_HIT = 0.1  # 每次复用扣分
_MAX_REUSE = 3  # 复用上限（超过判违规）


@dataclass(frozen=True)
class AssetCandidate:
    """provider 提供的候选素材（打分入口，纯值对象）。"""

    asset_id: str
    source: AssetSource
    license: AssetLicense
    query: str
    provider: str | None = None
    # §6.2 子分：语义/构图/分辨率/运动/颜色/品牌限制符合度，各 ∈ [0,1]
    semantic: float = 0.0
    composition: float = 0.0
    resolution: float = 0.0
    motion: float = 0.0
    color: float = 0.0
    brand_ok: float = 1.0  # 品牌限制符合度：1=不冲突，0=严重冲突
    reuse_count: int = 0  # 已被复用次数（跨 plan 累积传入，用于复用惩罚）


@dataclass(frozen=True)
class MatchWeights:
    """§6.2 匹配分权重（模板版本化，coefficients 均 ≥0）。"""

    template_version: str = "asset-v1"
    semantic: float = 0.28
    composition: float = 0.18
    resolution: float = 0.14
    motion: float = 0.10
    color: float = 0.10
    brand: float = 0.20  # 品牌/人物限制严重时相当于否决
    reuse_penalty: float = _REUSE_PENALTY_PER_HIT


DEFAULT_MATCH_WEIGHTS = MatchWeights()  # 模块级单例；函数默认参数直接引用避免每调用一次都构造


def match_score(cand: AssetCandidate, weights: MatchWeights = DEFAULT_MATCH_WEIGHTS) -> float:
    """§6.2 加权匹配分。复用次数越多扣分越重（复用惩罚）；clamp 到 [0,1]。"""
    raw = (
        weights.semantic * cand.semantic
        + weights.composition * cand.composition
        + weights.resolution * cand.resolution
        + weights.motion * cand.motion
        + weights.color * cand.color
        + weights.brand * cand.brand_ok
        - weights.reuse_penalty * cand.reuse_count
    )
    return max(0.0, min(1.0, raw))


def _placeholder_asset(slot: AssetPlanSlot) -> ResolvedAsset:
    """Fallback 占位：明确标记 is_fallback + PLACEHOLDER 许可，用后期人工替换。"""
    role = slot.fallback or AssetRole.PLACEHOLDER
    return ResolvedAsset(
        slot_id=slot.slot_id,
        asset_id=f"placeholder-{slot.slot_id}",
        source=AssetSource.PLACEHOLDER,
        license=AssetLicense(
            type=AssetLicenseType.PLACEHOLDER,
            holder="videoforge",
            notes=f"占位 fallback，人工替换为 {role.value}",
        ),
        query=slot.query,
        usage_start_ms=slot.start_ms,
        usage_end_ms=slot.end_ms,
        match_score=0.0,
        provider="placeholder",
        is_fallback=True,
    )


def resolve_asset_plan(
    slots: list[AssetPlanSlot],
    candidates_by_source: dict[AssetSource, list[AssetCandidate]],
    *,
    plan_id: str,
    created_at: datetime,
    source_transcript_id: str | None = None,
    weights: MatchWeights = DEFAULT_MATCH_WEIGHTS,
    accept_threshold: float = _MATCH_ACCEPT_THRESHOLD,
) -> AssetPlan:
    """按 §6.2 五级优先级解析每 slot；未命中走占位 fallback。resolved 顺序与 slots 一致。

    candidates_by_source 是每来源的候选列表（provider 层组装），本函数按优先级遍历、
    在 slot.allowed_sources 内查候选、取按 match_score 排序首个 ≥ 阈值者。跨 slot 追踪
    reuse_count（本 plan 内的复用），保证同一素材反复被选时的评分反映真实复用惩罚。
    """
    reused: dict[str, int] = {}  # asset_id → 本 plan 已使用次数
    resolved: list[ResolvedAsset] = []
    allowed_asset_sources = set(RESOLVER_PRIORITY)

    for slot in slots:
        slot_allowed = set(slot.allowed_sources)
        picked: ResolvedAsset | None = None
        for source in RESOLVER_PRIORITY:
            if source not in slot_allowed or source not in allowed_asset_sources:
                continue  # 该级来源不被允许，跳过
            pool = candidates_by_source.get(source, [])
            # 加上本 plan 内已复用次数再评分
            scored: list[tuple[float, AssetCandidate]] = []
            for c in pool:
                effective = AssetCandidate(
                    **{**c.__dict__, "reuse_count": c.reuse_count + reused.get(c.asset_id, 0)}
                )
                s = match_score(effective, weights)
                if s >= accept_threshold:
                    scored.append((s, effective))
            if not scored:
                continue
            # 高分优先，同分按 asset_id 确定性排序（可复现）
            scored.sort(key=lambda t: (-t[0], t[1].asset_id))
            score, chosen = scored[0]
            picked = ResolvedAsset(
                slot_id=slot.slot_id,
                asset_id=chosen.asset_id,
                source=chosen.source,
                license=chosen.license,
                query=chosen.query,
                usage_start_ms=slot.start_ms,
                usage_end_ms=slot.end_ms,
                match_score=score,
                reuse_count=reused.get(chosen.asset_id, 0) + 1,
                provider=chosen.provider,
            )
            reused[chosen.asset_id] = reused.get(chosen.asset_id, 0) + 1
            break

        resolved.append(picked if picked is not None else _placeholder_asset(slot))

    return AssetPlan(
        id=plan_id,
        source_transcript_id=source_transcript_id,
        slots=slots,
        resolved=resolved,
        weights_version=weights.template_version,
        created_at=created_at,
    )


class AssetPlanIssueKind(StrEnum):
    UNRESOLVED_SLOT = "UNRESOLVED_SLOT"  # slot 无 ResolvedAsset 且未走 fallback
    SOURCE_NOT_ALLOWED = "SOURCE_NOT_ALLOWED"  # 选中的来源不在 slot.allowed_sources 内
    LICENSE_INSUFFICIENT = "LICENSE_INSUFFICIENT"  # 商业许可到期或缺失
    USAGE_OUT_OF_SLOT = "USAGE_OUT_OF_SLOT"  # 使用区间超出 slot 时间范围
    REUSE_EXCEEDED = "REUSE_EXCEEDED"  # 单素材复用次数超上限


@dataclass(frozen=True)
class AssetPlanIssue:
    kind: AssetPlanIssueKind
    ref: str
    detail: str


def validate_asset_plan(
    plan: AssetPlan,
    *,
    now: datetime | None = None,
    max_reuse: int = _MAX_REUSE,
) -> list[AssetPlanIssue]:
    """§6.2 护栏：每 ResolvedAsset 必带来源/许可/检索词/使用区间；来源允许、许可有效、复用未超。"""
    issues: list[AssetPlanIssue] = []
    resolved_by_slot: dict[str, ResolvedAsset] = {}
    for r in plan.resolved:
        resolved_by_slot.setdefault(r.slot_id, r)

    for slot in plan.slots:
        r = resolved_by_slot.get(slot.slot_id)
        if r is None:
            issues.append(
                AssetPlanIssue(AssetPlanIssueKind.UNRESOLVED_SLOT, slot.slot_id, "无 ResolvedAsset")
            )
            continue
        # 来源合规。is_fallback 意味着"全部允许来源均未命中，走占位供人工替换"——这是设计好的
        # 逃生出口，占位来源本就不需要在 allowed_sources 内，故豁免；其他 issue（使用区间/许可
        # 等）仍照常检查。人工审通过后 fallback 会替换为真素材，届时来源自然会满足 allowed_sources。
        if not r.is_fallback and r.source not in slot.allowed_sources:
            issues.append(
                AssetPlanIssue(
                    AssetPlanIssueKind.SOURCE_NOT_ALLOWED, r.slot_id,
                    f"来源 {r.source.value} 未在 slot.allowed_sources",
                )
            )
        # 使用区间落在 slot 内
        if r.usage_start_ms < slot.start_ms or r.usage_end_ms > slot.end_ms:
            issues.append(
                AssetPlanIssue(
                    AssetPlanIssueKind.USAGE_OUT_OF_SLOT, r.slot_id,
                    f"使用区间 [{r.usage_start_ms},{r.usage_end_ms}] 超出 slot "
                    f"[{slot.start_ms},{slot.end_ms}]",
                )
            )
        # 许可到期
        if r.license.valid_until is not None and now is not None and r.license.valid_until < now:
            issues.append(
                AssetPlanIssue(
                    AssetPlanIssueKind.LICENSE_INSUFFICIENT, r.slot_id,
                    f"许可 {r.license.type.value} 已于 {r.license.valid_until.isoformat()} 过期",
                )
            )

    # 复用上限（同一 asset_id 出现次数超过阈值）
    counts: dict[str, int] = {}
    for r in plan.resolved:
        counts[r.asset_id] = counts.get(r.asset_id, 0) + 1
    for asset_id, n in counts.items():
        if n > max_reuse:
            issues.append(
                AssetPlanIssue(
                    AssetPlanIssueKind.REUSE_EXCEEDED, asset_id,
                    f"复用 {n} 次 > 上限 {max_reuse}",
                )
            )
    return issues


def is_valid_asset_plan(plan: AssetPlan, **kwargs) -> bool:
    return not validate_asset_plan(plan, **kwargs)
