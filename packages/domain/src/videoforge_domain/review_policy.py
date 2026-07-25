"""审核策略 + 版本签名（修改失效）+ Trusted Template 状态机（docs/modules/44 §1/§2/§12）。
纯函数、可复现。

- `compute_approval_signature(...)`：无密钥内容绑定摘要（sha256）。
- `is_approval_valid(decision, current_version, current_content_digest)`：**修改失效**——
  审批只对被签的确切版本+内容有效；一改即失效（§1.2/§13）。
- `review_disposition(policy, template_level, severities)`：策略 × 受信 × 严重级 → 处置。
- `evaluate_trust_upgrade` / `demote_on_change` / `promote_if_eligible`：§12 状态机。
- `validate_review_decision`：签名完整性 + 陈旧审批护栏。

**安全边界（与合同 docstring 一致）**：signature 是无密钥完整性绑定，**不是**密码学签名；
它保证"审批绑定到被审内容、被篡改可检测、一改即失效"，但**不提供不可否认性**（需
HMAC/非对称 + 密钥管理，属安全硬化项）。真实平台发布凭据是 stop-condition，不在本层。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from videoforge_contracts import (
    ReviewDecision,
    ReviewDecisionKind,
    ReviewPolicyMode,
    ReviewSeverity,
    TemplateTrustLevel,
    TemplateTrustState,
)

# §12：模板"关键字段"——变更这些即回退 NEW（超出字幕样式/Beat/Provider/发布元数据）
KEY_TEMPLATE_FIELDS: frozenset[str] = frozenset(
    {
        "subtitle_style",
        "beat",
        "beats",
        "provider",
        "providers",
        "publish_metadata",
        "publish_meta",
    }
)


class ReviewDisposition(StrEnum):
    """一个版本的审核处置结论。"""

    AUTO_APPROVE = "AUTO_APPROVE"  # 可自动通过（无需人工、无阻塞）
    NEEDS_REVIEW = "NEEDS_REVIEW"  # 需人工审核
    NEEDS_FIX = "NEEDS_FIX"  # ERROR：阻止发布，可修复后重跑
    BLOCKED = "BLOCKED"  # FATAL：不允许覆盖


class ReviewDecisionIssueKind(StrEnum):
    SIGNATURE_MISMATCH = "SIGNATURE_MISMATCH"  # 记录被篡改（签名对不上）
    APPROVAL_STALE = "APPROVAL_STALE"  # APPROVED 但已不匹配当前版本/内容（修改失效）


@dataclass(frozen=True)
class ReviewDecisionIssue:
    kind: ReviewDecisionIssueKind
    ref: str
    detail: str


def compute_approval_signature(
    *,
    entity_id: str,
    entity_version: int,
    content_digest: str,
    decision: ReviewDecisionKind,
    scope: str,
    reviewer_id: str,
    policy_snapshot_id: str,
) -> str:
    """无密钥内容绑定摘要（sha256）。同输入永远同签名——绑定审批到确切内容。"""
    payload = {
        "entity_id": entity_id,
        "entity_version": entity_version,
        "content_digest": content_digest,
        "decision": decision.value if isinstance(decision, ReviewDecisionKind) else str(decision),
        "scope": scope,
        "reviewer_id": reviewer_id,
        "policy_snapshot_id": policy_snapshot_id,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _signature_of(decision: ReviewDecision) -> str:
    return compute_approval_signature(
        entity_id=decision.entity_id,
        entity_version=decision.entity_version,
        content_digest=decision.content_digest,
        decision=decision.decision,
        scope=decision.scope.value,
        reviewer_id=decision.reviewer_id,
        policy_snapshot_id=decision.policy_snapshot_id,
    )


def signature_matches(decision: ReviewDecision) -> bool:
    """记录完整性：decision.signature 是否等于按其自身字段重算的签名。"""
    return decision.signature == _signature_of(decision)


def is_approval_valid(
    decision: ReviewDecision,
    *,
    current_version: int,
    current_content_digest: str,
    current_entity_id: str | None = None,
) -> bool:
    """审批当前是否有效。**任何修改即失效**（§1.2/§13）。

    有效 ⟺ 是 APPROVED 且 签名完整 且 版本、内容摘要都匹配当前。
    `current_entity_id` 给定时还要求 entity 一致（自包含的实体绑定，防调用方按错 key 取
    到别的 entity 的审批——纵深防御；entity_id 本已进签名，此为门层再拦一道）。
    """
    if decision.decision is not ReviewDecisionKind.APPROVED:
        return False
    if not signature_matches(decision):
        return False
    if current_entity_id is not None and decision.entity_id != current_entity_id:
        return False
    if decision.entity_version != current_version:
        return False
    if decision.content_digest != current_content_digest:
        return False
    return True


def publish_severity_gate(
    severities: Iterable[ReviewSeverity],
    *,
    warning_blocks: bool = False,
) -> ReviewDisposition:
    """§2 严重级 → 发布门。FATAL 不可覆盖；ERROR 阻止可修；WARNING 看策略；INFO 放行。"""
    sev = set(severities)
    if ReviewSeverity.FATAL in sev:
        return ReviewDisposition.BLOCKED
    if ReviewSeverity.ERROR in sev:
        return ReviewDisposition.NEEDS_FIX
    if ReviewSeverity.WARNING in sev and warning_blocks:
        return ReviewDisposition.NEEDS_REVIEW
    return ReviewDisposition.AUTO_APPROVE


def requires_human_review(
    mode: ReviewPolicyMode,
    *,
    template_level: TemplateTrustLevel,
) -> bool:
    """§12 策略 × 受信：是否需人工（不含严重级门，严重级由 publish_severity_gate 处理）。"""
    if mode is ReviewPolicyMode.ALWAYS:
        return True
    if mode is ReviewPolicyMode.NEW_TEMPLATE_ONLY:
        return template_level is TemplateTrustLevel.NEW
    return False  # AUTO


def review_disposition(
    mode: ReviewPolicyMode,
    *,
    template_level: TemplateTrustLevel,
    severities: Iterable[ReviewSeverity] = (),
    warning_blocks: bool = False,
) -> ReviewDisposition:
    """综合处置：严重级门优先（FATAL/ERROR 先拦），否则按策略决定人工/自动。"""
    gate = publish_severity_gate(severities, warning_blocks=warning_blocks)
    if gate in (ReviewDisposition.BLOCKED, ReviewDisposition.NEEDS_FIX):
        return gate  # 阻塞级优先，覆盖策略
    if requires_human_review(mode, template_level=template_level):
        return ReviewDisposition.NEEDS_REVIEW
    return gate  # AUTO_APPROVE 或 warning→NEEDS_REVIEW（已在 gate 里）


def evaluate_trust_upgrade(
    state: TemplateTrustState,
) -> tuple[bool, list[str]]:
    """§12 NEW → TRUSTED 资格评估。返回 (是否够格, 未达标项)。"""
    s, c = state.stats, state.criteria
    failed: list[str] = []
    if s.approved_render_count < c.min_approved_renders:
        failed.append("approved_render_count")
    if s.recent_fatal_count > c.max_recent_fatal:
        failed.append("recent_fatal_count")
    if s.recent_error_rate > c.max_error_rate:
        failed.append("recent_error_rate")
    if not s.qa_meets_standard:
        failed.append("qa_meets_standard")
    if not s.publish_success_ok:
        failed.append("publish_success_ok")
    if not s.duplicate_publish_ok:
        failed.append("duplicate_publish_ok")
    if c.require_owner_approval and not s.owner_approved:
        failed.append("owner_approved")
    return (not failed), failed


def promote_if_eligible(state: TemplateTrustState) -> TemplateTrustState:
    """若当前 NEW 且够格 → 升 TRUSTED；否则原样返回（幂等）。"""
    if state.level is not TemplateTrustLevel.NEW:
        return state
    eligible, _ = evaluate_trust_upgrade(state)
    if not eligible:
        return state
    return state.model_copy(update={"level": TemplateTrustLevel.TRUSTED})


def demote_on_change(
    state: TemplateTrustState,
    changed_fields: Iterable[str],
) -> TemplateTrustState:
    """§12：变更关键字段（字幕样式/Beat/Provider/发布元数据）→ 回退 NEW；否则原样。"""
    changed = {f.lower() for f in changed_fields}
    if changed & KEY_TEMPLATE_FIELDS:
        if state.level is TemplateTrustLevel.NEW:
            return state
        return state.model_copy(update={"level": TemplateTrustLevel.NEW})
    return state


def validate_review_decision(
    decision: ReviewDecision,
    *,
    current_version: int | None = None,
    current_content_digest: str | None = None,
) -> list[ReviewDecisionIssue]:
    """审核决定护栏：签名完整性 + （给了当前上下文时）陈旧审批。"""
    issues: list[ReviewDecisionIssue] = []
    if not signature_matches(decision):
        issues.append(
            ReviewDecisionIssue(
                ReviewDecisionIssueKind.SIGNATURE_MISMATCH,
                decision.id,
                "signature 与按记录字段重算的不一致——记录可能被篡改",
            )
        )
    if (
        decision.decision is ReviewDecisionKind.APPROVED
        and current_version is not None
        and current_content_digest is not None
        and (
            decision.entity_version != current_version
            or decision.content_digest != current_content_digest
        )
    ):
        issues.append(
            ReviewDecisionIssue(
                ReviewDecisionIssueKind.APPROVAL_STALE,
                decision.id,
                f"APPROVED 绑定 v{decision.entity_version} 但当前 v{current_version}"
                "（内容/版本已变，旧审批失效）",
            )
        )
    return issues


def is_valid_review_decision(
    decision: ReviewDecision,
    *,
    current_version: int | None = None,
    current_content_digest: str | None = None,
) -> bool:
    return not validate_review_decision(
        decision,
        current_version=current_version,
        current_content_digest=current_content_digest,
    )
