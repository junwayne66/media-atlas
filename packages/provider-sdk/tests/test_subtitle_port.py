"""VF-402 Forced Alignment provider-sdk 测试。"""

from videoforge_provider_sdk import (
    FakeForcedAlignmentProvider,
    ForcedAlignmentErrorCode,
    ForcedAlignmentProvider,
    ForcedAlignmentRequest,
    ForcedAlignmentStatus,
    UnconfiguredForcedAlignmentProvider,
)


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeForcedAlignmentProvider(), ForcedAlignmentProvider)


def test_unconfigured_satisfies_protocol() -> None:
    assert isinstance(UnconfiguredForcedAlignmentProvider(), ForcedAlignmentProvider)


def test_unconfigured_returns_unconfigured() -> None:
    r = UnconfiguredForcedAlignmentProvider().align(
        ForcedAlignmentRequest(text="hi", language="en-US", start_ms=0, end_ms=1000),
    )
    assert r.status is ForcedAlignmentStatus.UNCONFIGURED
    assert r.error_code is ForcedAlignmentErrorCode.MODEL_UNAVAILABLE
    assert r.words == []


def test_fake_align_zh_by_chars() -> None:
    r = FakeForcedAlignmentProvider().align(
        ForcedAlignmentRequest(text="你好世界", language="zh-CN", start_ms=0, end_ms=4000),
    )
    assert r.status is ForcedAlignmentStatus.OK
    assert [w.text for w in r.words] == ["你", "好", "世", "界"]
    # 时间单调 + 覆盖 [0,4000]
    assert r.words[0].start_ms == 0
    assert r.words[-1].end_ms == 4000
    for a, b in zip(r.words, r.words[1:], strict=False):
        assert a.end_ms == b.start_ms


def test_fake_align_en_by_words() -> None:
    r = FakeForcedAlignmentProvider().align(
        ForcedAlignmentRequest(text="hello world", language="en-US",
                                  start_ms=1000, end_ms=3000),
    )
    assert r.status is ForcedAlignmentStatus.OK
    assert [w.text for w in r.words] == ["hello", "world"]
    assert r.words[0].start_ms == 1000
    assert r.words[-1].end_ms == 3000


def test_fake_confidence_fixed_not_faked_high() -> None:
    """安全底线：Fake 不假装高置信；固定 0.5，让 karaoke 决策"知道"这是伪造对齐。"""
    r = FakeForcedAlignmentProvider().align(
        ForcedAlignmentRequest(text="hello", language="en-US", start_ms=0, end_ms=1000),
    )
    assert all(w.confidence == 0.5 for w in r.words)


def test_fake_empty_text_returns_empty_words_ok() -> None:
    r = FakeForcedAlignmentProvider().align(
        ForcedAlignmentRequest(text="   ", language="zh-CN", start_ms=0, end_ms=1000),
    )
    assert r.status is ForcedAlignmentStatus.OK
    assert r.words == []


def test_fake_end_before_start_fails() -> None:
    r = FakeForcedAlignmentProvider().align(
        ForcedAlignmentRequest(text="x", language="zh-CN",
                                  start_ms=1000, end_ms=500),
    )
    assert r.status is ForcedAlignmentStatus.FAILED
    assert r.error_code is ForcedAlignmentErrorCode.UNKNOWN


def test_fake_deep_copy_input() -> None:
    """修改 request 不能改变结果（deep-copy 保护）。"""
    req = ForcedAlignmentRequest(text="hello", language="en-US",
                                    start_ms=0, end_ms=1000)
    r = FakeForcedAlignmentProvider().align(req)
    # frozen dataclass 无法改；构造后再对结果修改也不能影响 provider（无内部状态）
    r.words.clear() if r.words else None
    r2 = FakeForcedAlignmentProvider().align(req)
    assert len(r2.words) > 0


def test_fake_health_check_ok() -> None:
    r = FakeForcedAlignmentProvider().health_check()
    assert r.status is ForcedAlignmentStatus.OK
