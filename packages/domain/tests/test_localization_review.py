"""VF-407 本地化审核 domain 测试：§12 一致性 + 发布门 + §13 局部重跑 + 句级批准护栏。"""

from datetime import UTC, datetime

import pytest

from videoforge_contracts import (
    LocalizationQACheck,
    LocalizationQAFinding,
    LocalizationReview,
    QASeverity,
    ReRunStage,
    ReviewState,
    SentenceReviewDecision,
)
from videoforge_domain import (
    ConsistencyPair,
    LocalizationReviewIssueKind,
    ReRunEditKind,
    aggregate_localization_qa,
    check_negation_consistency,
    check_number_consistency,
    compute_rerun_scope,
    is_valid_localization_review,
    run_consistency_checks,
    sentence_review_queue,
    validate_localization_publish_gate,
    validate_localization_review,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _finding(sid: str, sev: QASeverity,
             check: LocalizationQACheck = LocalizationQACheck.TTS_GAP) -> LocalizationQAFinding:
    return LocalizationQAFinding(
        sentence_id=sid, check=check, severity=sev, detail="x",
    )


# --- §12 数字一致 --------------------------------------------------------

def test_numbers_match_returns_none():
    assert check_number_consistency("s", "有 5 个核 120W", "5 cores 120W") is None


def test_dropped_number_is_blocker():
    f = check_number_consistency("s", "有 5 个核 120W", "cores 120W")
    assert f is not None
    assert f.check is LocalizationQACheck.NUMBER_CONSISTENCY
    assert f.severity is QASeverity.BLOCKER
    assert "5" in f.detail


def test_added_number_is_blocker():
    f = check_number_consistency("s", "有核", "有 8 核")
    assert f is not None and f.severity is QASeverity.BLOCKER


def test_changed_number_is_blocker():
    f = check_number_consistency("s", "5 核", "6 cores")
    assert f is not None and f.severity is QASeverity.BLOCKER


def test_thousands_separator_normalized():
    # 1,000 == 1000（去千分位逗号）→ 一致
    assert check_number_consistency("s", "1,000 次", "1000 times") is None


# --- §12 否定一致 --------------------------------------------------------

def test_negation_match_returns_none():
    assert check_negation_consistency(
        "s", "这不快", "this is not fast",
        source_lang="zh-CN", target_lang="en-US",
    ) is None


def test_dropped_negation_is_major():
    f = check_negation_consistency(
        "s", "这不快", "this is fast",
        source_lang="zh-CN", target_lang="en-US",
    )
    assert f is not None
    assert f.check is LocalizationQACheck.NEGATION_CONSISTENCY
    assert f.severity is QASeverity.MAJOR


def test_english_contraction_negation_counted():
    f = check_negation_consistency(
        "s", "它有效", "it doesn't work",
        source_lang="zh-CN", target_lang="en-US",
    )
    # 源 0 否定 vs 译 1 否定（doesn't）→ 不一致
    assert f is not None and f.severity is QASeverity.MAJOR


# --- 发布门 --------------------------------------------------------------

def test_gate_blocks_on_blocker():
    assert validate_localization_publish_gate([_finding("s", QASeverity.BLOCKER)]) is False


def test_gate_blocks_on_too_many_majors():
    majors = [_finding(f"s{i}", QASeverity.MAJOR) for i in range(4)]  # > 3
    assert validate_localization_publish_gate(majors) is False


def test_gate_passes_with_few_majors_and_minors():
    fs = [_finding("s0", QASeverity.MAJOR), _finding("s1", QASeverity.MINOR),
          _finding("s2", QASeverity.INFO)]
    assert validate_localization_publish_gate(fs) is True


def test_aggregate_computes_gate_and_preserves_findings():
    findings = run_consistency_checks(
        [ConsistencyPair("s", "有 5 核", "no cores", "zh-CN", "en-US")]
    )
    rep = aggregate_localization_qa(
        findings, id="r", localization_variant_id="v",
        reviewed_sentence_ids=["s"], created_at=_T0,
    )
    assert rep.pass_or_block is False  # 数字 BLOCKER
    assert len(rep.findings) == len(findings)


# --- §13 局部重跑（headline）--------------------------------------------

def test_rerun_scope_only_edited_sentence():
    scope = compute_rerun_scope(["s2"], ["s1", "s2", "s3"])
    assert scope.edited_sentence_ids == ("s2",)
    assert set(scope.per_sentence_stages) == {"s2"}
    assert scope.per_sentence_stages["s2"] == (
        ReRunStage.TTS, ReRunStage.SUBTITLE, ReRunStage.LIPSYNC,
    )
    assert scope.global_stages == (ReRunStage.AUDIO_MIX, ReRunStage.RENDER)
    assert scope.unaffected_sentence_ids == ("s1", "s3")


def test_rerun_scope_never_reruns_translation_or_other_sentences():
    scope = compute_rerun_scope(["s2"], ["s1", "s2", "s3"])
    all_stages = [
        st for stages in scope.per_sentence_stages.values() for st in stages
    ] + list(scope.global_stages)
    # 改译文本身是输入 → TRANSLATION 绝不重跑
    assert ReRunStage.TRANSLATION not in all_stages
    # 其它句零阶段
    for sid in scope.unaffected_sentence_ids:
        assert sid not in scope.per_sentence_stages


def test_rerun_scope_scoping_property_fuzz():
    all_ids = [f"s{i}" for i in range(8)]
    for edited in ([], ["s0"], ["s3", "s5"], all_ids):
        scope = compute_rerun_scope(edited, all_ids)
        edited_set = set(edited)
        # per_sentence 只含被编辑句
        assert set(scope.per_sentence_stages) == edited_set
        # unaffected = all - edited，且并集覆盖全部
        assert set(scope.unaffected_sentence_ids) == set(all_ids) - edited_set
        assert set(scope.unaffected_sentence_ids) | edited_set == set(all_ids)
        # 空编辑 → 无全局阶段
        assert bool(scope.global_stages) == bool(edited)


def test_rerun_scope_rejects_unknown_sentence():
    with pytest.raises(ValueError, match="不在 all_sentence_ids"):
        compute_rerun_scope(["ghost"], ["s1", "s2"])


def test_rerun_scope_voice_change_same_downstream():
    scope = compute_rerun_scope(["s1"], ["s1", "s2"], edit_kind=ReRunEditKind.VOICE_CHANGE)
    assert scope.per_sentence_stages["s1"] == (
        ReRunStage.TTS, ReRunStage.SUBTITLE, ReRunStage.LIPSYNC,
    )


# --- 审核队列 + 护栏 -----------------------------------------------------

def test_review_queue_dedups_by_sentence():
    rep = aggregate_localization_qa(
        [_finding("a", QASeverity.MINOR), _finding("a", QASeverity.MAJOR),
         _finding("b", QASeverity.MINOR)],
        id="r", localization_variant_id="v", reviewed_sentence_ids=["a", "b"],
        created_at=_T0,
    )
    assert sentence_review_queue(rep) == ["a", "b"]


def test_cannot_approve_sentence_with_blocker():
    findings = [_finding("s", QASeverity.BLOCKER, LocalizationQACheck.NUMBER_CONSISTENCY)]
    review = LocalizationReview(
        id="rv", localization_variant_id="v",
        decisions=[SentenceReviewDecision(sentence_id="s", state=ReviewState.APPROVED)],
        created_at=_T0,
    )
    kinds = {i.kind for i in validate_localization_review(review, findings)}
    assert LocalizationReviewIssueKind.APPROVED_OVER_BLOCKER in kinds


def test_editing_or_rejecting_a_blocker_sentence_is_allowed():
    findings = [_finding("s", QASeverity.BLOCKER)]
    review = LocalizationReview(
        id="rv", localization_variant_id="v",
        decisions=[
            SentenceReviewDecision(sentence_id="s", state=ReviewState.EDITED,
                                    edited_text="修好的译文"),
        ],
        created_at=_T0,
    )
    assert is_valid_localization_review(review, findings)


def test_approving_a_clean_sentence_is_valid():
    findings = [_finding("other", QASeverity.BLOCKER)]
    review = LocalizationReview(
        id="rv", localization_variant_id="v",
        decisions=[SentenceReviewDecision(sentence_id="s", state=ReviewState.APPROVED)],
        created_at=_T0,
    )
    assert is_valid_localization_review(review, findings)  # s 无 BLOCKER
