"""P4 Exit 验收 —— 数字/产品名/否定一致率 100%（docs/modules/43 §13 第 1 条）。

20 中英样本共 40 句忠实译对：纯数字/否定一致（domain）+ 浅层专名保留（Fake provider）
全部零发现 → 一致率 100%；发布门放行。非空跑护栏：注入篡改必被 BLOCKER/MAJOR 抓住。
"""

from __future__ import annotations

from datetime import UTC, datetime

from p4_samples import SAMPLES

from videoforge_contracts import QASeverity
from videoforge_domain import (
    ConsistencyPair,
    aggregate_localization_qa,
    check_number_consistency,
    run_consistency_checks,
)
from videoforge_provider_sdk import (
    ConsistencyCheckRequest,
    FakeLocalizationConsistencyProvider,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _all_findings():
    fake = FakeLocalizationConsistencyProvider()
    findings = []
    for smp in SAMPLES:
        for s in smp.sentences:
            findings.extend(run_consistency_checks(
                [ConsistencyPair(s.sentence_id, s.source, s.target,
                                  s.source_lang, s.target_lang)]
            ))
            findings.extend(fake.check(ConsistencyCheckRequest(
                s.sentence_id, s.source, s.target, s.source_lang,
                s.target_lang, s.entities,
            )).findings)
    return findings


def test_twenty_samples_forty_sentences():
    assert len(SAMPLES) == 20
    assert sum(len(s.sentences) for s in SAMPLES) == 40


def test_number_negation_proper_noun_consistency_is_100_percent():
    findings = _all_findings()
    assert findings == [], (
        "忠实译对应零一致性发现，实际："
        + "; ".join(f"{f.sentence_id}:{f.check.value}:{f.detail}" for f in findings)
    )


def test_publish_gate_passes_for_clean_samples():
    report = aggregate_localization_qa(
        _all_findings(), id="p4-qa", localization_variant_id="v",
        reviewed_sentence_ids=[s.sentence_id for smp in SAMPLES for s in smp.sentences],
        created_at=_T0,
    )
    assert report.pass_or_block is True


def test_checks_are_not_vacuous_number_tamper_caught():
    # 从每个含数字的句删掉一个数字 → 必被 NUMBER_CONSISTENCY BLOCKER 抓
    tampered = 0
    for smp in SAMPLES:
        for s in smp.sentences:
            src_nums = check_number_consistency(s.sentence_id, s.source, s.target)
            if src_nums is not None:
                continue  # 本就不一致的跳过（不应发生）
            # 构造去掉所有数字的"坏译文"
            import re
            bad_target = re.sub(r"\d", "", s.target)
            if bad_target == s.target:
                continue  # 无数字句跳过
            f = check_number_consistency(s.sentence_id, s.source, bad_target)
            assert f is not None and f.severity is QASeverity.BLOCKER
            tampered += 1
    assert tampered >= 15, f"应有足够多含数字句被抓，实际 {tampered}"


def test_checks_are_not_vacuous_proper_noun_drop_caught():
    # 有 verbatim 专名的句：把专名从译文抹掉 → Fake 必报 MAJOR
    fake = FakeLocalizationConsistencyProvider()
    caught = 0
    for smp in SAMPLES:
        for s in smp.sentences:
            if not s.entities:
                continue
            bad = s.target
            for e in s.entities:
                bad = bad.replace(e, "")
            r = fake.check(ConsistencyCheckRequest(
                s.sentence_id, s.source, bad, s.source_lang, s.target_lang, s.entities,
            ))
            assert r.findings and all(
                f.severity is QASeverity.MAJOR for f in r.findings
            )
            caught += 1
    assert caught >= 5, f"应有足够多含专名句被抓，实际 {caught}"
