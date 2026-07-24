"""时长拟合改写端口 + Fake（docs/modules/43 §8 步 1：LLM 改写更短/更长，Claim 不变）。

`rewrite(text, language, direction, target) -> rewritten_text + estimated_ms`，产出喂给
domain `plan_duration_fit` 的 `rewritten_estimate_ms`（§8 步 1）。

**红线**：改写**绝不改变 Claim**。`FakeDurationRewriteProvider` 只删除非词汇性犹豫音
（um/uh/呃/嗯…），从不删除承载事实的内容，也从不删除 `must_keep_terms`；因此
`claims_unchanged=True` 是诚实的。无法安全缩短（无犹豫音可删）或方向为 LONGER（Fake 不
凭空扩写）时返回 `NO_CHANGE_NEEDED`，绝不伪造内容。

provider-sdk 只依赖 contracts，不 import domain（层级隔离）；时长估算内联副本与
`videoforge_domain.rewrite.estimate_duration_ms` 数值一致（zh 非空白字符/5 + en 词/2.5）。
"""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

_EN_TOKEN_RE = re.compile(r"\S+")

# 填充词只收**非词汇性的犹豫音**（vocable）——这类不承载任何 Claim，删了 claims_unchanged=True
# 才诚实。刻意排除内容可用词（like/well/actually…英文、那个/这个/其实…中文）。
# 删除是**整词/边界感知**的（见 `_strip_filler_tokens`）：只丢被空白/标点分隔的完整犹豫音
# token，绝不做子串 `.replace`——否则中文会切进内容词（'唔知道'→'知道' Claim 反转，
# verifier round-2 揭示）。真实按语义安全缩短需 LLM → stop-condition 延后。
# 注意：只收非词汇性犹豫音。刻意**不含** 'err'（英文动词 "to err is human"）与 '唔'
# （粤语否定 "唔好"=不好）——它们虽像语气词却是内容词，删了会改 Claim（verifier round-3）。
# 'erm' 才是真犹豫音，保留。
_FILLER: frozenset[str] = frozenset({
    # 英文犹豫音
    "um", "umm", "uh", "uhh", "uhm", "erm", "hmm", "mmm",
    # 中文纯语气/犹豫词
    "呃", "呃呃", "嗯", "嗯嗯", "唉", "呀", "哦",
})

_CHARS_PER_SEC_ZH = 5.0
_WORDS_PER_SEC_EN = 2.5


def _is_boundary(ch: str) -> bool:
    """空白或标点视为 token 边界（中英统一；CJK 标点也是 Unicode P*）。"""
    return ch.isspace() or unicodedata.category(ch).startswith("P")


def _strip_filler_tokens(text: str, keep: tuple[str, ...]) -> tuple[str, int]:
    """删除被边界分隔的**完整**犹豫音 token；返回 (结果, 删除个数)。

    切成 word/sep 交替块，只丢"整块恰好等于某犹豫音"的 word——因此永不切进内容词
    （'唔知道' 是一个 word token ≠ '唔'，不动；'他就是说谎' 同理）。删词后清理由此产生的
    行首/行尾/连续分隔符。删除数为 0 时原样返回（不做无谓的空白裁剪，保持诚实）。
    """
    keep_lower = {k.lower() for k in keep}
    chunks: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        boundary = _is_boundary(text[i])
        j = i + 1
        while j < n and _is_boundary(text[j]) == boundary:
            j += 1
        chunks.append(("sep" if boundary else "word", text[i:j]))
        i = j

    dropped = 0
    kept: list[tuple[str, str]] = []
    for kind, txt in chunks:
        if (
            kind == "word"
            and txt.lower() in _FILLER
            and txt.lower() not in keep_lower
        ):
            dropped += 1
            continue
        kept.append((kind, txt))
    if dropped == 0:
        return text, 0

    out: list[str] = []
    prev_sep = True  # 视行首为分隔 → 跳过前导 sep
    for kind, txt in kept:
        if kind == "sep":
            if prev_sep:  # 跳过前导/连续分隔
                continue
            out.append(txt)
            prev_sep = True
        else:
            out.append(txt)
            prev_sep = False
    if out and prev_sep:  # 去掉尾随分隔
        out.pop()
    return "".join(out), dropped


class DurationRewriteDirection(StrEnum):
    SHORTER = "SHORTER"
    LONGER = "LONGER"


class DurationRewriteStatus(StrEnum):
    OK = "OK"  # 产出了长度调整后的改写
    NO_CHANGE_NEEDED = "NO_CHANGE_NEEDED"  # 无可安全调整（不伪造）
    FAILED = "FAILED"
    UNCONFIGURED = "UNCONFIGURED"


class DurationRewriteErrorCode(StrEnum):
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    CLAIMS_AT_RISK = "CLAIMS_AT_RISK"  # 无法在不动 Claim 的前提下改写
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DurationRewriteRequest:
    """一次长度定向改写请求。"""

    sentence_id: str
    text: str
    language: str
    current_estimate_ms: int
    target_ms: int
    direction: DurationRewriteDirection
    must_keep_terms: tuple[str, ...] = ()  # 术语/Claim 关键词，绝不删


@dataclass(frozen=True)
class DurationRewriteResult:
    status: DurationRewriteStatus
    sentence_id: str
    rewritten_text: str | None = None
    estimated_ms: int | None = None
    claims_unchanged: bool = True
    error_code: DurationRewriteErrorCode | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class DurationRewriteProvider(Protocol):
    """§8 步 1 长度定向改写端口。"""

    name: str

    def rewrite(self, request: DurationRewriteRequest) -> DurationRewriteResult: ...

    def health_check(self) -> DurationRewriteResult: ...


class UnconfiguredDurationRewriteProvider:
    """诚实占位：无真实改写 LLM，绝不产出改写（真 LLM 属 stop-condition 延后）。"""

    def __init__(self, *, name: str = "duration_rewrite.unconfigured") -> None:
        self.name = name

    def rewrite(self, request: DurationRewriteRequest) -> DurationRewriteResult:
        return DurationRewriteResult(
            status=DurationRewriteStatus.UNCONFIGURED,
            sentence_id=request.sentence_id,
            error_code=DurationRewriteErrorCode.ENGINE_UNAVAILABLE,
            error_detail=f"provider {self.name!r} 未配置真实改写 LLM",
        )

    def health_check(self) -> DurationRewriteResult:
        return DurationRewriteResult(
            status=DurationRewriteStatus.UNCONFIGURED,
            sentence_id="",
            error_code=DurationRewriteErrorCode.ENGINE_UNAVAILABLE,
        )


def _estimate_ms(text: str, language: str) -> int:
    """内联时长估算——与 domain.rewrite.estimate_duration_ms 数值一致。"""
    if language.lower().startswith("zh"):
        units = sum(1 for c in text if not c.isspace())
        rate = _CHARS_PER_SEC_ZH
    else:
        units = len(_EN_TOKEN_RE.findall(text))
        rate = _WORDS_PER_SEC_EN
    if units == 0:
        return 0
    return int(round(units / rate * 1000))


class FakeDurationRewriteProvider:
    """确定性 Fake：仅删填充词做"更短"改写，Claim 不变；LONGER 不凭空扩写。

    - **SHORTER**：删除**边界分隔的完整**犹豫音 token（中英统一、绝不子串捕获——见
      `_strip_filler_tokens`），但**从不删** `must_keep_terms` 命中的内容；重算估算。
      无犹豫音可删 → `NO_CHANGE_NEEDED`（诚实，不伪造）。
    - **LONGER**：Fake 不安全扩写 → `NO_CHANGE_NEEDED` + warning（真 LLM 才做）。
    - `claims_unchanged` 恒 True（只删犹豫音，不动事实）。
    - deep-copy 输入；无内部状态。
    """

    def __init__(self, *, name: str = "duration_rewrite.fake",
                  supported_languages: tuple[str, ...] = ("zh-CN", "en-US")) -> None:
        self.name = name
        self.supported_languages = supported_languages

    def rewrite(self, request: DurationRewriteRequest) -> DurationRewriteResult:
        req = deepcopy(request)
        if req.language not in self.supported_languages:
            return DurationRewriteResult(
                status=DurationRewriteStatus.FAILED,
                sentence_id=req.sentence_id,
                error_code=DurationRewriteErrorCode.UNSUPPORTED_LANGUAGE,
                error_detail=f"provider {self.name!r} 未支持语言 {req.language!r}",
            )
        if req.direction is DurationRewriteDirection.LONGER:
            return DurationRewriteResult(
                status=DurationRewriteStatus.NO_CHANGE_NEEDED,
                sentence_id=req.sentence_id,
                rewritten_text=req.text,
                estimated_ms=req.current_estimate_ms,
                warnings=["Fake 不凭空扩写（真 LLM 才做 LONGER）；原文原样返回"],
            )
        # SHORTER：边界感知删除完整犹豫音 token
        shortened, dropped = _strip_filler_tokens(req.text, req.must_keep_terms)
        if dropped == 0 or not shortened.strip():
            return DurationRewriteResult(
                status=DurationRewriteStatus.NO_CHANGE_NEEDED,
                sentence_id=req.sentence_id,
                rewritten_text=req.text,
                estimated_ms=req.current_estimate_ms,
                warnings=["无犹豫音可安全删除；不缩短（Claim 不变优先）"],
            )
        return DurationRewriteResult(
            status=DurationRewriteStatus.OK,
            sentence_id=req.sentence_id,
            rewritten_text=shortened,
            estimated_ms=_estimate_ms(shortened, req.language),
            claims_unchanged=True,
            warnings=["Fake 改写：仅删犹豫音，Claim 未变"],
        )

    def health_check(self) -> DurationRewriteResult:
        return DurationRewriteResult(
            status=DurationRewriteStatus.OK, sentence_id="",
        )


__all__ = [
    "DurationRewriteDirection",
    "DurationRewriteErrorCode",
    "DurationRewriteProvider",
    "DurationRewriteRequest",
    "DurationRewriteResult",
    "DurationRewriteStatus",
    "FakeDurationRewriteProvider",
    "UnconfiguredDurationRewriteProvider",
]
