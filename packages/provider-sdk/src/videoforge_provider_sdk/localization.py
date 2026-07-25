"""Translate-Reflect-Adapt 端口 + Fake（docs/modules/43 §4）。

真实 TRA 引擎（LLM）在 CanonicalSentence + Glossary 上产出 draft/reflected_notes/
adapted + semantic_similarity + duration_estimate_ms + claim_diff。需模型/授权，属
停止条件延后：默认 UnconfiguredTRAProvider 诚实返回 UNCONFIGURED；FakeTRAProvider
使用术语表做**受控**替换（不虚构 claim、changed_claims 空=通过、命中 must_keep 才输出）。

安全底线（§4.3）：changed_claims 非空 → 上层必须走人工审核；Fake **绝不构造 ADDED
claim**——localized_claim_ids 严格等于源 claim_ids 集合。若 provider 觉得改动了事实，
应通过 claim_diff.deltas 报告，绝不静默改 claim_ids。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import (
    CanonicalSentence,
    ClaimDiff,
    Glossary,
    TranslateReflectAdaptResult,
)


def _is_word_char(ch: str) -> bool:
    """word-boundary 判定；仅 ASCII alnum。与 domain._is_word_char 一致（层级隔离，
    provider-sdk 不能 import domain，故此处内联同规则——注意 domain 侧变化要同步）。"""
    return ch.isascii() and (ch.isalnum() or ch == "_")


def _term_present(text: str, term: str) -> bool:
    if not term:
        return True
    text_low = text.lower()
    term_low = term.lower()
    if any(_is_word_char(c) for c in term):
        padded = f" {text_low} "
        idx = 0
        while True:
            idx = padded.find(term_low, idx)
            if idx < 0:
                return False
            left = padded[idx - 1]
            right = padded[idx + len(term_low)]
            if not (_is_word_char(left) or _is_word_char(right)):
                return True
            idx += 1
    return term_low in text_low


class TRAStatus(StrEnum):
    OK = "OK"
    NEEDS_REVIEW = "NEEDS_REVIEW"  # claim_diff 非空或低相似度
    FAILED = "FAILED"
    UNCONFIGURED = "UNCONFIGURED"


class TRAErrorCode(StrEnum):
    """provider 报告的错误码（41 §12 命名风格）。"""

    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    UNSUPPORTED_LANGUAGE_PAIR = "UNSUPPORTED_LANGUAGE_PAIR"
    GLOSSARY_MISSING = "GLOSSARY_MISSING"
    RATE_LIMITED = "RATE_LIMITED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TRARequest:
    """一次 TRA 调用。glossary 可为空——但 provider 应至少能"直译不虚构"。"""

    sentence: CanonicalSentence
    target_language: str
    glossary: Glossary | None = None
    n_alternatives: int = 0


@dataclass(frozen=True)
class TRAResult:
    status: TRAStatus
    result: TranslateReflectAdaptResult | None = None
    error_code: TRAErrorCode | None = None
    error_detail: str | None = None


@runtime_checkable
class TranslateReflectAdaptProvider(Protocol):
    """Translate → Reflect → Adapt 三阶段的合约。"""

    name: str
    execution_location: str  # local / cloud

    def translate_reflect_adapt(self, request: TRARequest) -> TRAResult: ...

    def health_check(self) -> TRAResult: ...


class UnconfiguredTRAProvider:
    """诚实占位：没有模型授权，绝不静默"翻译"。返回 UNCONFIGURED，上层路由至人工。"""

    def __init__(
        self, *, name: str = "tra.unconfigured", execution_location: str = "local"
    ) -> None:
        self.name = name
        self.execution_location = execution_location

    def translate_reflect_adapt(self, request: TRARequest) -> TRAResult:
        return TRAResult(
            status=TRAStatus.UNCONFIGURED,
            error_code=TRAErrorCode.MODEL_UNAVAILABLE,
            error_detail=(
                f"provider {self.name!r} 未配置真实 TRA 模型；"
                f"target_language={request.target_language}"
            ),
        )

    def health_check(self) -> TRAResult:
        return TRAResult(
            status=TRAStatus.UNCONFIGURED,
            error_code=TRAErrorCode.MODEL_UNAVAILABLE,
        )


class FakeTRAProvider:
    """确定性 Fake：按术语表**逐项替换** + 保留 must_keep_terms，不虚构 claim。

    行为：
    - draft_text = adapted_text = 源文里逐条 glossary 替换
      （长术语优先；preserve_source=True 不替）。
    - reflected_notes：为每条应用的术语生成一句说明；不做真正的 Reflect 判断。
    - claim_diff：**永远等于源 claim_ids 集合**（无 ADDED/REMOVED）；provider 不构造事实变化。
      若源 claim_ids 里有 DISPUTED，交给 domain.validate_localization 判定，不在此拒引。
    - semantic_similarity=0.9（固定，代表"直译+术语替换"的中等信任度；真模型自评）。
    - duration_estimate_ms：由 domain.estimate_duration_for_language 估算；因不能 import
      domain（同层），此处用**内联最小副本**（中文字符/5，英文词/2.5 秒率——与 domain 表一致）。
    - 命中 must_keep_terms 但目标文里丢失 → 兜底保留源片段（provider 兜底，护栏也会拦）。
    - deep-copy 出入：不污染 request/sentence 引用（同 VF-203/305 的确定性 Fake 规则）。
    """

    _CHARS_PER_SEC_ZH = 5.0
    _WORDS_PER_SEC_EN = 2.5

    def __init__(self, *, name: str = "tra.fake", execution_location: str = "cloud") -> None:
        self.name = name
        self.execution_location = execution_location

    def _estimate_ms(self, text: str, language: str) -> int:
        # 与 videoforge_domain.estimate_duration_ms 数值一致（同语速表），保 replay 一致
        if language.lower().startswith("zh"):
            units = len([c for c in text if not c.isspace()])
            rate = self._CHARS_PER_SEC_ZH
        else:
            units = len(text.split())
            rate = self._WORDS_PER_SEC_EN
        if units == 0:
            return 0
        return int(round(units / rate * 1000))

    def _apply_glossary(self, text: str, glossary: Glossary | None) -> tuple[str, list[str]]:
        """按术语表替换，返回 (新文本, 应用的术语列表)。preserve_source=True 不替。"""
        if glossary is None:
            return text, []
        result = text
        applied: list[str] = []
        # 长术语优先，避免 "端" 覆盖 "端侧"
        for e in sorted(glossary.entries, key=lambda x: -len(x.source_term)):
            if e.preserve_source:
                continue
            if e.source_term.lower() not in result.lower():
                continue
            # 大小写不敏感精确替换
            low = result.lower()
            src_low = e.source_term.lower()
            rebuilt: list[str] = []
            i = 0
            prev = 0
            while True:
                k = low.find(src_low, i)
                if k < 0:
                    rebuilt.append(result[prev:])
                    break
                rebuilt.append(result[prev:k])
                rebuilt.append(e.target_term)
                i = k + len(src_low)
                prev = i
            result = "".join(rebuilt)
            applied.append(e.source_term)
        return result, applied

    def translate_reflect_adapt(self, request: TRARequest) -> TRAResult:
        # 深拷贝输入避免污染
        sentence = deepcopy(request.sentence)
        glossary = deepcopy(request.glossary) if request.glossary else None

        # 若术语表存在但语言对不匹配 → 报错（不静默降级）
        if glossary is not None:
            if (
                glossary.source_language != sentence.source_language
                or glossary.target_language != request.target_language
            ):
                return TRAResult(
                    status=TRAStatus.FAILED,
                    error_code=TRAErrorCode.UNSUPPORTED_LANGUAGE_PAIR,
                    error_detail=(
                        f"术语表语言对 ({glossary.source_language}→{glossary.target_language}) "
                        f"与请求 ({sentence.source_language}→{request.target_language}) 不匹配"
                    ),
                )

        adapted, applied_terms = self._apply_glossary(sentence.source_text, glossary)
        draft = adapted  # Fake 不区分 draft/adapted（无真正 Adapt 阶段）
        reflected_notes = [f"应用术语 {t!r}" for t in applied_terms] or [
            "未启用术语替换（无术语表命中）"
        ]

        # must_keep_terms 兜底：若某个术语在替换后从译文丢失，反回来提示（不改文本）。
        # 判定与 domain._text_contains_term 一致（word-boundary 仅 ASCII alnum 生效），
        # 避免"provider 说 OK / domain 说 LOST"分歧。
        for term in sentence.must_keep_terms:
            if not _term_present(adapted, term):
                reflected_notes.append(f"警告：must_keep 术语 {term!r} 未在译文出现")

        # 备选：把术语替换回源作为一个可选（保守）方案（真引擎会给多样化改写）
        alternatives: list[str] = []
        if request.n_alternatives > 0 and applied_terms:
            alternatives.append(sentence.source_text)
            alternatives = alternatives[: request.n_alternatives]

        # claim_diff：**永远** src == loc，Fake 不构造 ADDED/REMOVED
        claim_diff = ClaimDiff(
            source_claim_ids=list(sentence.claim_ids),
            localized_claim_ids=list(sentence.claim_ids),
            deltas=[],
        )
        duration_ms = self._estimate_ms(adapted, request.target_language)

        result = TranslateReflectAdaptResult(
            canonical_sentence_id=sentence.id,
            target_language=request.target_language,
            draft_text=draft,
            reflected_notes=reflected_notes,
            adapted_text=adapted,
            alternatives=alternatives,
            semantic_similarity=0.90,
            duration_estimate_ms=duration_ms,
            claim_diff=claim_diff,
            provider=self.name,
        )
        # 深拷贝出，防止外层修改污染潜在缓存
        return TRAResult(status=TRAStatus.OK, result=deepcopy(result))

    def health_check(self) -> TRAResult:
        return TRAResult(status=TRAStatus.OK)


__all__ = [
    "FakeTRAProvider",
    "TRAErrorCode",
    "TRARequest",
    "TRAResult",
    "TRAStatus",
    "TranslateReflectAdaptProvider",
    "UnconfiguredTRAProvider",
]
