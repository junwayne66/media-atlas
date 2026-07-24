"""VF-401 provider-sdk TRA 端口 + Fake 测试。"""

from datetime import UTC, datetime

import pytest

from videoforge_contracts import (
    CanonicalSentence,
    Glossary,
    GlossaryEntry,
    RhetoricalBeatKind,
)
from videoforge_provider_sdk import (
    FakeTRAProvider,
    TRAErrorCode,
    TranslateReflectAdaptProvider,
    TRARequest,
    TRAStatus,
    UnconfiguredTRAProvider,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _cs(text: str = "端侧模型 20ms 完成推理", claims: list[str] | None = None,
         must_keep: list[str] | None = None, lang: str = "zh-CN") -> CanonicalSentence:
    return CanonicalSentence(
        id="cs-0", beat_slot_id="b", role=RhetoricalBeatKind.EVIDENCE,
        source_language=lang, source_text=text, semantic_intent="i",
        claim_ids=claims or [],
        source_time_range_start_ms=0, source_time_range_end_ms=3000,
        target_duration_ms=3000, must_keep_terms=must_keep or [],
    )


def _glossary_zh_en() -> Glossary:
    return Glossary(
        id="g", source_language="zh-CN", target_language="en-US",
        entries=[
            GlossaryEntry(source_term="端侧", target_term="on-device"),
            GlossaryEntry(source_term="20ms", target_term="20 ms"),
            GlossaryEntry(source_term="Qwen", target_term="Qwen",
                            preserve_source=True),
        ],
        created_at=_T0,
    )


# —— Protocol 一致性 ——

def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeTRAProvider(), TranslateReflectAdaptProvider)


def test_unconfigured_satisfies_protocol() -> None:
    assert isinstance(UnconfiguredTRAProvider(), TranslateReflectAdaptProvider)


# —— Unconfigured：诚实报告 ——

def test_unconfigured_never_translates() -> None:
    r = UnconfiguredTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(), target_language="en-US"),
    )
    assert r.status is TRAStatus.UNCONFIGURED
    assert r.result is None
    assert r.error_code is TRAErrorCode.MODEL_UNAVAILABLE


def test_unconfigured_health() -> None:
    r = UnconfiguredTRAProvider().health_check()
    assert r.status is TRAStatus.UNCONFIGURED


# —— Fake：术语替换 + 保留 ——

def test_fake_applies_glossary() -> None:
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(), target_language="en-US",
                     glossary=_glossary_zh_en()),
    )
    assert r.status is TRAStatus.OK and r.result is not None
    assert "on-device" in r.result.adapted_text
    assert "20 ms" in r.result.adapted_text


def test_fake_preserve_source_terms_untouched() -> None:
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(text="Qwen 是端侧模型"), target_language="en-US",
                     glossary=_glossary_zh_en()),
    )
    assert r.result is not None
    assert "Qwen" in r.result.adapted_text  # preserve_source=True → 不替


def test_fake_long_term_first_no_partial_overlap() -> None:
    """'端侧' 应先替，避免 '端' 单独替换后剩下 'edge侧'。"""
    gl = Glossary(
        id="g", source_language="zh-CN", target_language="en-US",
        entries=[
            GlossaryEntry(source_term="端", target_term="edge"),
            GlossaryEntry(source_term="端侧", target_term="on-device"),
        ],
        created_at=_T0,
    )
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(text="端侧模型很好"), target_language="en-US",
                     glossary=gl),
    )
    assert r.result is not None
    assert "on-device" in r.result.adapted_text
    assert "edge侧" not in r.result.adapted_text


# —— Fake：不虚构 claim ——

def test_fake_never_adds_or_removes_claims() -> None:
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(claims=["c1", "c2"]), target_language="en-US"),
    )
    assert r.result is not None
    assert r.result.claim_diff.deltas == []
    assert r.result.claim_diff.source_claim_ids == ["c1", "c2"]
    assert r.result.claim_diff.localized_claim_ids == ["c1", "c2"]


# —— Fake：must_keep 兜底提示 ——

def test_fake_warns_when_must_keep_term_lost() -> None:
    """术语表把 'Qwen' 保留、但 must_keep 里加 '2GB'，adapted 里可能没有 '2GB' → 出警。"""
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(
            sentence=_cs(text="端侧模型很好", must_keep=["2GB"]),
            target_language="en-US", glossary=_glossary_zh_en(),
        ),
    )
    assert r.result is not None
    assert any("2GB" in note or "must_keep" in note for note in r.result.reflected_notes)


# —— Fake：语言对不匹配 → FAILED ——

def test_fake_rejects_mismatched_language_pair() -> None:
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(text="hi", lang="en-US"), target_language="zh-CN",
                     glossary=_glossary_zh_en()),  # 术语表是 zh→en
    )
    assert r.status is TRAStatus.FAILED
    assert r.error_code is TRAErrorCode.UNSUPPORTED_LANGUAGE_PAIR


# —— Fake：无术语表也能返回 ——

def test_fake_works_without_glossary() -> None:
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(), target_language="en-US"),
    )
    assert r.status is TRAStatus.OK and r.result is not None
    assert r.result.adapted_text == r.result.draft_text  # 无替换 → adapted == source
    assert "未启用" in r.result.reflected_notes[0]


# —— 时长估算与语言相关 ——

def test_fake_duration_scales_by_target_language() -> None:
    # 短英文 → 词少 → 少 ms
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(text="hi", lang="en-US"), target_language="en-US"),
    )
    assert r.result is not None
    assert r.result.duration_estimate_ms > 0


# —— 深拷贝防污染 ——

def test_fake_does_not_mutate_input_sentence() -> None:
    s = _cs(text="Qwen 端侧模型", claims=["c1"])
    original_claims = list(s.claim_ids)
    FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=s, target_language="en-US", glossary=_glossary_zh_en()),
    )
    assert s.claim_ids == original_claims
    assert s.source_text == "Qwen 端侧模型"


def test_fake_result_isolated_from_caller_mutation() -> None:
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(claims=["c1"]), target_language="en-US"),
    )
    assert r.result is not None
    # 调用方修改返回结果不能污染 provider（provider 无内部缓存本例；此处防未来加缓存回归）
    r.result.claim_diff.localized_claim_ids.append("evil")
    r2 = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(claims=["c1"]), target_language="en-US"),
    )
    assert r2.result is not None
    assert r2.result.claim_diff.localized_claim_ids == ["c1"]


# —— Fake 语义相似度稳定 ——

def test_fake_similarity_stable() -> None:
    r = FakeTRAProvider().translate_reflect_adapt(
        TRARequest(sentence=_cs(), target_language="en-US"),
    )
    assert r.result is not None
    assert r.result.semantic_similarity == pytest.approx(0.90)
