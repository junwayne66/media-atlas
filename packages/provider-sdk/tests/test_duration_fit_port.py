"""VF-405 provider-sdk 时长改写：Unconfigured / Fake / Claim 不变红线。"""

from videoforge_domain import estimate_duration_ms  # 跨层一致性交叉校验
from videoforge_provider_sdk import (
    DurationRewriteDirection,
    DurationRewriteErrorCode,
    DurationRewriteProvider,
    DurationRewriteRequest,
    DurationRewriteStatus,
    FakeDurationRewriteProvider,
    UnconfiguredDurationRewriteProvider,
)


def _req(
    text: str, lang: str, direction=DurationRewriteDirection.SHORTER, *, keep=()
) -> DurationRewriteRequest:
    return DurationRewriteRequest(
        sentence_id="s",
        text=text,
        language=lang,
        current_estimate_ms=3000,
        target_ms=2000,
        direction=direction,
        must_keep_terms=keep,
    )


def test_providers_satisfy_protocol():
    assert isinstance(FakeDurationRewriteProvider(), DurationRewriteProvider)
    assert isinstance(UnconfiguredDurationRewriteProvider(), DurationRewriteProvider)


def test_unconfigured_never_rewrites():
    r = UnconfiguredDurationRewriteProvider().rewrite(_req("um hello", "en-US"))
    assert r.status is DurationRewriteStatus.UNCONFIGURED
    assert r.rewritten_text is None
    assert r.error_code is DurationRewriteErrorCode.ENGINE_UNAVAILABLE


def test_fake_shorter_removes_english_vocables():
    r = FakeDurationRewriteProvider().rewrite(_req("um uh this is the point", "en-US"))
    assert r.status is DurationRewriteStatus.OK
    assert r.rewritten_text == "this is the point"
    assert r.claims_unchanged is True


def test_fake_shorter_removes_chinese_vocables():
    # 标点分隔的完整语气词才删（真实 ASR 常带标点）
    r = FakeDurationRewriteProvider().rewrite(_req("嗯，这个模型很快", "zh-CN"))
    assert r.status is DurationRewriteStatus.OK
    assert r.rewritten_text == "这个模型很快"  # 只删被分隔的 嗯，内容保留
    assert r.claims_unchanged is True


def test_fake_does_not_capture_content_word_substring():
    # verifier round-1：'就是说' 若在填充表会切进 '就是说谎'。犹豫音表 + 整词删除下不再发生。
    r = FakeDurationRewriteProvider().rewrite(_req("他就是说谎的人", "zh-CN"))
    assert r.status is DurationRewriteStatus.NO_CHANGE_NEEDED
    assert r.rewritten_text == "他就是说谎的人"  # 内容一字不动


def test_fake_zh_interjection_glued_in_word_not_captured():
    # verifier round-2 残留反例：'唔知道'（不知道）曾被子串删成 '知道'（知道）—— Claim 反转。
    # 整词/边界感知删除下，'唔知道' 是一个 token ≠ '唔'，不动。
    for glued in ("唔知道", "唉声叹气", "嗯哼一声"):
        r = FakeDurationRewriteProvider().rewrite(_req(glued, "zh-CN"))
        assert r.status is DurationRewriteStatus.NO_CHANGE_NEEDED, glued
        assert r.rewritten_text == glued


def test_fake_filler_set_excludes_lexical_content_words():
    # verifier round-3：'err'（英文动词）与 '唔'（粤语否定）虽像语气词却是内容词，
    # 删了会改 Claim。已从 _FILLER 剔除——整词删除也救不了内容词落在集合里。
    p = FakeDurationRewriteProvider()
    r = p.rewrite(_req("to err is human", "en-US"))
    assert r.status is DurationRewriteStatus.NO_CHANGE_NEEDED
    assert r.rewritten_text == "to err is human"  # 不再变 "to is human"
    r2 = p.rewrite(_req("唔 好", "zh-CN"))
    assert r2.status is DurationRewriteStatus.NO_CHANGE_NEEDED
    assert r2.rewritten_text == "唔 好"  # "不好" 不再被反转成 "好"
    # 'erm'（真犹豫音）仍在表内，仍删
    r3 = p.rewrite(_req("erm this is fine", "en-US"))
    assert r3.status is DurationRewriteStatus.OK
    assert r3.rewritten_text == "this is fine"


def test_fake_estimate_matches_domain_estimate():
    # provider 内联估算必须与 domain.estimate_duration_ms 逐位一致
    r = FakeDurationRewriteProvider().rewrite(_req("um uh this is the point", "en-US"))
    assert r.estimated_ms == estimate_duration_ms(r.rewritten_text, "en-US")
    rz = FakeDurationRewriteProvider().rewrite(_req("嗯，这个模型很快", "zh-CN"))
    assert rz.estimated_ms == estimate_duration_ms(rz.rewritten_text, "zh-CN")


def test_fake_no_filler_makes_no_change():
    r = FakeDurationRewriteProvider().rewrite(_req("the model runs on device", "en-US"))
    assert r.status is DurationRewriteStatus.NO_CHANGE_NEEDED
    assert r.rewritten_text == "the model runs on device"  # 不伪造缩短


def test_fake_never_removes_must_keep_term():
    # 'um' 恰是犹豫音，但作为 must_keep_terms → 保护不删；同句其它犹豫音 'uh' 仍删
    r = FakeDurationRewriteProvider().rewrite(_req("um uh the brand", "en-US", keep=("um",)))
    assert r.status is DurationRewriteStatus.OK
    assert r.rewritten_text == "um the brand"  # 'uh' 删，'um' 因保护留下
    assert "um" in r.rewritten_text.split()


def test_fake_longer_does_not_fabricate():
    r = FakeDurationRewriteProvider().rewrite(
        _req("short", "en-US", DurationRewriteDirection.LONGER)
    )
    assert r.status is DurationRewriteStatus.NO_CHANGE_NEEDED
    assert r.rewritten_text == "short"  # 原样返回，绝不凭空扩写


def test_fake_unsupported_language_fails():
    r = FakeDurationRewriteProvider().rewrite(_req("hola", "es-ES"))
    assert r.status is DurationRewriteStatus.FAILED
    assert r.error_code is DurationRewriteErrorCode.UNSUPPORTED_LANGUAGE


def test_fake_is_deterministic():
    p = FakeDurationRewriteProvider()
    req = _req("um uh this is the point", "en-US")
    a = p.rewrite(req)
    b = p.rewrite(req)
    assert (a.status, a.rewritten_text, a.estimated_ms) == (
        b.status,
        b.rewritten_text,
        b.estimated_ms,
    )
    # 输入未被 provider 改动
    assert req.text == "um uh this is the point"
