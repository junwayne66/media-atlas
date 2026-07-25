"""本地化契约（docs/modules/43 §3-§4）。

- CanonicalScript：语言无关的中性稿（源 + must_keep_terms + Claim + 时长预算）。
  翻译修改不覆盖它，而是产 LocalizedSentence（§3）。
- Glossary/GlossaryEntry：术语表（产品名/模型名/数值/单位/发音提示）。
- TranslateReflectAdaptResult：TRA 三阶段的合同产出，含 semantic_similarity、
  duration_estimate_ms、changed_claims（§4.3）；changed_claims 非空必须人工审核。
- LocalizedSentence / LocalizationVariant：每目标语言一份 Variant，共享 Canonical。
- ClaimDiff：source_claims 与 localized_claims 的结构化 diff（reason 帮 QA/人工排错）。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import ClaimSourceStatus, RhetoricalBeatKind


class GlossaryEntry(ContractModel):
    """术语条目：source_term 在目标语言里锁定为 target_term；可选发音提示。

    - `preserve_source=True`：目标译文里必须原样保留（产品名/模型名 通常如此）；
      与 target_term 二选一——preserve_source 时 target_term 强制等于 source_term。
    - `pronunciation`：给 TTS 参考的读音（IPA/拼音/自然拼写），本身不参与译文替换。
    - `notes`：给译者/审核的说明（如"缩写读作字母"）。
    """

    source_term: str = Field(min_length=1)
    target_term: str = Field(min_length=1)
    preserve_source: bool = False
    pronunciation: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_preserve(self) -> "GlossaryEntry":
        if self.preserve_source and self.target_term != self.source_term:
            raise ValueError("preserve_source=True 时 target_term 必须等于 source_term")
        return self


class Glossary(ContractModel):
    """术语表（一对语言）。entries 里 source_term + source_language + target_language 唯一。"""

    id: str = Field(min_length=1)
    source_language: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    entries: list[GlossaryEntry] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    created_at: datetime

    @model_validator(mode="after")
    def _check_unique_source(self) -> "Glossary":
        seen: set[str] = set()
        for e in self.entries:
            key = e.source_term
            if key in seen:
                raise ValueError(f"术语表 source_term 重复：{key}")
            seen.add(key)
        return self


class CanonicalSentence(ContractModel):
    """中性稿的一句：语言无关的语义 + 时长预算 + 引用 Claim + must_keep_terms（§3）。

    翻译修改不直接覆盖这里；派生 LocalizedSentence 承载译文。
    """

    id: str = Field(min_length=1)
    beat_slot_id: str = Field(min_length=1)
    role: RhetoricalBeatKind
    speaker_id: str | None = None
    source_language: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    semantic_intent: str = Field(min_length=1, description="本句的功能/意图（抽象，语言无关）")
    claim_ids: list[str] = Field(default_factory=list)
    source_time_range_start_ms: int = Field(ge=0)
    source_time_range_end_ms: int = Field(ge=0)
    target_duration_ms: int = Field(ge=0)
    must_keep_terms: list[str] = Field(
        default_factory=list, description="必须保留的术语（引用 Glossary.source_term）"
    )
    pronunciation_hints: list[str] = Field(default_factory=list)
    visual_dependencies: list[str] = Field(
        default_factory=list, description="引用同期镜头/文本轨 id"
    )
    edit_flexibility: float = Field(
        default=0.15, ge=0.0, le=1.0, description="允许缩/扩比例（±%），供时长拟合"
    )

    @model_validator(mode="after")
    def _check_span(self) -> "CanonicalSentence":
        if self.source_time_range_end_ms < self.source_time_range_start_ms:
            raise ValueError("source_time_range_end_ms 必须 ≥ start_ms")
        return self


class CanonicalScript(ContractModel):
    """中性稿：单份、语言无关；每目标语言从此派生 LocalizationVariant。"""

    id: str = Field(min_length=1)
    script_version_id: str | None = None
    source_language: str = Field(min_length=1)
    sentences: list[CanonicalSentence] = Field(default_factory=list)
    total_duration_ms: int | None = Field(default=None, ge=0)
    created_at: datetime


class ClaimDelta(ContractModel):
    """一次 Claim 层面的变化。reason 供 QA/人工快速判断（漏译/添加事实/否定翻转 等）。"""

    kind: str = Field(
        min_length=1, description="ADDED / REMOVED / MUTATED / NEGATION_FLIP / NUMBER_MISMATCH"
    )
    claim_id: str | None = None
    detail: str = Field(min_length=1)


class ClaimDiff(ContractModel):
    """source_claims 与 localized_claims 的差异汇总（§4.3）。empty → 与源一致。"""

    source_claim_ids: list[str] = Field(default_factory=list)
    localized_claim_ids: list[str] = Field(default_factory=list)
    deltas: list[ClaimDelta] = Field(default_factory=list)


class TranslateReflectAdaptResult(ContractModel):
    """TRA 三阶段的合同产出（§4）。

    - draft_text：Translate 的初译。
    - reflected_notes：Reflect 阶段的问题清单（漏译/事实/否定/因果/文风），非阻断。
    - adapted_text：Adapt 阶段的最终稿；不改 Claim，控语速/句长/钩子/口语度。
    - semantic_similarity ∈ [0,1]：adapted 与源的语义相似度估计（Provider 自评）。
    - duration_estimate_ms：按目标语言语速估算的时长。
    - claim_diff：不为空必须走人工审核（§4.3）。
    - alternatives：为目标时长生成的 A/B 候选文本（0..N）。
    """

    canonical_sentence_id: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    draft_text: str = Field(min_length=1)
    reflected_notes: list[str] = Field(default_factory=list)
    adapted_text: str = Field(min_length=1)
    alternatives: list[str] = Field(default_factory=list)
    semantic_similarity: float = Field(ge=0.0, le=1.0)
    duration_estimate_ms: int = Field(ge=0)
    claim_diff: ClaimDiff = Field(default_factory=ClaimDiff)
    provider: str = Field(min_length=1)


class LocalizedSentence(ContractModel):
    """派生的本地化句：绑到 CanonicalSentence，承载译文 + 引用的 Claim（可能被 diff 变更）。

    `needs_review` 由 domain.validate_localization 决定（Claim diff 非空、术语失守、
    低相似度、超时长预算等触发）；provider 层不直接置 True。
    """

    id: str = Field(min_length=1)
    canonical_sentence_id: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    text: str = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)
    claim_source_status: ClaimSourceStatus = ClaimSourceStatus.UNVERIFIED
    tra_result_id: str | None = None
    duration_estimate_ms: int = Field(ge=0)
    semantic_similarity: float = Field(ge=0.0, le=1.0)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)


class LocalizationVariant(ContractModel):
    """一个目标语言的本地化产物：共享 Canonical + Glossary，含逐句 LocalizedSentence。"""

    id: str = Field(min_length=1)
    canonical_script_id: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    glossary_id: str | None = None
    sentences: list[LocalizedSentence] = Field(default_factory=list)
    provider: str = Field(min_length=1)
    total_duration_estimate_ms: int | None = Field(default=None, ge=0)
    created_at: datetime
