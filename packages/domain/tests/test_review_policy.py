"""VF-501 审核策略 domain 测试：版本签名/修改失效 + 策略处置 + Trusted Template 状态机。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    ReviewDecision,
    ReviewDecisionKind,
    ReviewPolicyMode,
    ReviewScope,
    ReviewSeverity,
    TemplateTrustCriteria,
    TemplateTrustLevel,
    TemplateTrustState,
    TemplateTrustStats,
)
from videoforge_domain import (
    ReviewDecisionIssueKind,
    ReviewDisposition,
    compute_approval_signature,
    demote_on_change,
    evaluate_trust_upgrade,
    is_approval_valid,
    promote_if_eligible,
    publish_severity_gate,
    requires_human_review,
    review_disposition,
    signature_matches,
    validate_review_decision,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)
_NEW = TemplateTrustLevel.NEW
_TRUSTED = TemplateTrustLevel.TRUSTED


def _decision(*, version: int = 7, digest: str = "abc",
              kind: ReviewDecisionKind = ReviewDecisionKind.APPROVED,
              sign: bool = True, signature: str = "x") -> ReviewDecision:
    sig = compute_approval_signature(
        entity_id="var_1", entity_version=version, content_digest=digest,
        decision=kind, scope="VARIANT", reviewer_id="u1", policy_snapshot_id="p1",
    ) if sign else signature
    return ReviewDecision(
        id="rd1", decision=kind, scope=ReviewScope.VARIANT, entity_id="var_1",
        entity_version=version, content_digest=digest, reviewer_id="u1",
        policy_snapshot_id="p1", signature=sig, created_at=_T0,
    )


def _stats(**over) -> TemplateTrustStats:
    base = dict(
        approved_render_count=24, recent_fatal_count=0, recent_error_rate=0.02,
        qa_meets_standard=True, publish_success_ok=True,
        duplicate_publish_ok=True, owner_approved=True,
    )
    base.update(over)
    return TemplateTrustStats(**base)


def _state(level=_NEW, **stats_over) -> TemplateTrustState:
    return TemplateTrustState(
        template_id="t", template_version=3, level=level,
        stats=_stats(**stats_over), criteria=TemplateTrustCriteria(), updated_at=_T0,
    )


# --- 签名 + 修改失效（安全核心）------------------------------------------

def test_signature_is_deterministic():
    kw = dict(entity_id="e", entity_version=1, content_digest="d",
              decision=ReviewDecisionKind.APPROVED, scope="VARIANT",
              reviewer_id="u", policy_snapshot_id="p")
    assert compute_approval_signature(**kw) == compute_approval_signature(**kw)


def test_valid_approval_matches_current():
    d = _decision(version=7, digest="abc")
    assert signature_matches(d)
    assert is_approval_valid(d, current_version=7, current_content_digest="abc")


def test_approval_invalid_when_version_bumped():
    d = _decision(version=7, digest="abc")
    assert not is_approval_valid(d, current_version=8, current_content_digest="abc")


def test_approval_invalid_when_content_changed():
    d = _decision(version=7, digest="abc")
    assert not is_approval_valid(d, current_version=7, current_content_digest="XYZ")


def test_approval_invalid_for_wrong_entity_when_bound():
    # 纵深防御：给定 current_entity_id 时，别的 entity 的审批不能通过
    d = _decision(version=7, digest="abc")  # entity_id="var_1"
    assert is_approval_valid(
        d, current_version=7, current_content_digest="abc", current_entity_id="var_1")
    assert not is_approval_valid(
        d, current_version=7, current_content_digest="abc",
        current_entity_id="var_OTHER")


def test_rejected_decision_never_valid():
    d = _decision(kind=ReviewDecisionKind.REJECTED)
    assert not is_approval_valid(d, current_version=7, current_content_digest="abc")


def test_tampered_record_detected_by_signature():
    # 篡改版本号却复用旧签名 → 签名对不上 → 检测到；即使匹配 current 也无效
    d = _decision(version=7, digest="abc")
    tampered = d.model_copy(update={"entity_version": 9})
    assert not signature_matches(tampered)
    assert not is_approval_valid(tampered, current_version=9, current_content_digest="abc")


def test_resigning_tampered_still_fails_if_not_current():
    # 攻击者重算签名让记录自洽，但版本仍不匹配当前 → 修改失效仍拦
    resigned = _decision(version=7, digest="abc")  # 一致（自签）记录
    # 当前实体已到 v8：即使记录自洽，绑定的是 v7 → 无效
    assert signature_matches(resigned)
    assert not is_approval_valid(resigned, current_version=8, current_content_digest="abc")


def test_validate_flags_signature_mismatch_and_stale():
    d = _decision(version=7, digest="abc")
    tampered = d.model_copy(update={"entity_version": 8})
    kinds = {i.kind for i in validate_review_decision(
        tampered, current_version=8, current_content_digest="abc")}
    assert ReviewDecisionIssueKind.SIGNATURE_MISMATCH in kinds

    stale = _decision(version=7, digest="abc")  # 自洽但已过时
    kinds2 = {i.kind for i in validate_review_decision(
        stale, current_version=9, current_content_digest="abc")}
    assert ReviewDecisionIssueKind.APPROVAL_STALE in kinds2


def test_clean_current_decision_has_no_issues():
    d = _decision(version=7, digest="abc")
    assert validate_review_decision(
        d, current_version=7, current_content_digest="abc") == []


# --- §2 严重级门 ---------------------------------------------------------

def test_severity_gate():
    assert publish_severity_gate([ReviewSeverity.FATAL]) is ReviewDisposition.BLOCKED
    assert publish_severity_gate([ReviewSeverity.ERROR]) is ReviewDisposition.NEEDS_FIX
    assert publish_severity_gate(
        [ReviewSeverity.WARNING], warning_blocks=True) is ReviewDisposition.NEEDS_REVIEW
    assert publish_severity_gate(
        [ReviewSeverity.WARNING], warning_blocks=False) is ReviewDisposition.AUTO_APPROVE
    assert publish_severity_gate([ReviewSeverity.INFO]) is ReviewDisposition.AUTO_APPROVE
    assert publish_severity_gate([]) is ReviewDisposition.AUTO_APPROVE


def test_fatal_beats_error_when_both_present():
    assert publish_severity_gate(
        [ReviewSeverity.ERROR, ReviewSeverity.FATAL]) is ReviewDisposition.BLOCKED


# --- §12 策略 × 受信 -----------------------------------------------------

def test_requires_human_review_by_mode():
    assert requires_human_review(ReviewPolicyMode.ALWAYS, template_level=_TRUSTED)
    assert requires_human_review(ReviewPolicyMode.NEW_TEMPLATE_ONLY, template_level=_NEW)
    assert not requires_human_review(
        ReviewPolicyMode.NEW_TEMPLATE_ONLY, template_level=_TRUSTED)
    assert not requires_human_review(ReviewPolicyMode.AUTO, template_level=_NEW)


def test_review_disposition_combinations():
    # 阻塞级优先，覆盖策略
    assert review_disposition(
        ReviewPolicyMode.AUTO, template_level=_TRUSTED,
        severities=[ReviewSeverity.FATAL]) is ReviewDisposition.BLOCKED
    assert review_disposition(
        ReviewPolicyMode.AUTO, template_level=_TRUSTED,
        severities=[ReviewSeverity.ERROR]) is ReviewDisposition.NEEDS_FIX
    # 无阻塞：按策略
    assert review_disposition(
        ReviewPolicyMode.ALWAYS, template_level=_TRUSTED) is ReviewDisposition.NEEDS_REVIEW
    assert review_disposition(
        ReviewPolicyMode.NEW_TEMPLATE_ONLY, template_level=_NEW,
    ) is ReviewDisposition.NEEDS_REVIEW
    assert review_disposition(
        ReviewPolicyMode.NEW_TEMPLATE_ONLY, template_level=_TRUSTED,
    ) is ReviewDisposition.AUTO_APPROVE
    assert review_disposition(
        ReviewPolicyMode.AUTO, template_level=_TRUSTED) is ReviewDisposition.AUTO_APPROVE


# --- §12 Trusted Template 状态机 ----------------------------------------

def test_all_good_stats_are_eligible():
    ok, failed = evaluate_trust_upgrade(_state())
    assert ok and failed == []


def test_each_criterion_can_fail():
    cases = {
        "approved_render_count": _state(approved_render_count=5),
        "recent_fatal_count": _state(recent_fatal_count=1),
        "recent_error_rate": _state(recent_error_rate=0.5),
        "qa_meets_standard": _state(qa_meets_standard=False),
        "publish_success_ok": _state(publish_success_ok=False),
        "duplicate_publish_ok": _state(duplicate_publish_ok=False),
        "owner_approved": _state(owner_approved=False),
    }
    for name, st in cases.items():
        ok, failed = evaluate_trust_upgrade(st)
        assert not ok and name in failed


def test_promote_new_to_trusted_when_eligible():
    assert promote_if_eligible(_state(level=_NEW)).level is _TRUSTED


def test_promote_keeps_new_when_ineligible():
    assert promote_if_eligible(_state(level=_NEW, approved_render_count=1)).level is _NEW


def test_promote_is_idempotent_on_trusted():
    st = _state(level=_TRUSTED)
    assert promote_if_eligible(st).level is _TRUSTED


def test_demote_on_key_field_change():
    st = _state(level=_TRUSTED)
    for field in ("beat", "subtitle_style", "provider", "publish_metadata"):
        assert demote_on_change(st, [field]).level is _NEW


def test_no_demote_on_non_key_change():
    st = _state(level=_TRUSTED)
    assert demote_on_change(st, ["caption_text", "thumbnail"]).level is _TRUSTED


def test_demote_new_stays_new():
    st = _state(level=_NEW)
    assert demote_on_change(st, ["beat"]).level is _NEW
