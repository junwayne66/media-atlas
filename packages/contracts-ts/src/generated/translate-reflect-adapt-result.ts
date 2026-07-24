/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AdaptedText = string;
export type Alternatives = string[];
export type CanonicalSentenceId = string;
export type ClaimId = string | null;
export type Detail = string;
/**
 * ADDED / REMOVED / MUTATED / NEGATION_FLIP / NUMBER_MISMATCH
 */
export type Kind = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Deltas = ClaimDelta[];
export type LocalizedClaimIds = string[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type SourceClaimIds = string[];
export type DraftText = string;
export type DurationEstimateMs = number;
export type Provider = string;
export type ReflectedNotes = string[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type SemanticSimilarity = number;
export type TargetLanguage = string;

/**
 * TRA 三阶段的合同产出（§4）。
 *
 * - draft_text：Translate 的初译。
 * - reflected_notes：Reflect 阶段的问题清单（漏译/事实/否定/因果/文风），非阻断。
 * - adapted_text：Adapt 阶段的最终稿；不改 Claim，控语速/句长/钩子/口语度。
 * - semantic_similarity ∈ [0,1]：adapted 与源的语义相似度估计（Provider 自评）。
 * - duration_estimate_ms：按目标语言语速估算的时长。
 * - claim_diff：不为空必须走人工审核（§4.3）。
 * - alternatives：为目标时长生成的 A/B 候选文本（0..N）。
 */
export interface TranslateReflectAdaptResult {
  adapted_text: AdaptedText;
  alternatives?: Alternatives;
  canonical_sentence_id: CanonicalSentenceId;
  claim_diff?: ClaimDiff;
  draft_text: DraftText;
  duration_estimate_ms: DurationEstimateMs;
  provider: Provider;
  reflected_notes?: ReflectedNotes;
  schema_version?: SchemaVersion2;
  semantic_similarity: SemanticSimilarity;
  target_language: TargetLanguage;
}
/**
 * source_claims 与 localized_claims 的差异汇总（§4.3）。empty → 与源一致。
 */
export interface ClaimDiff {
  deltas?: Deltas;
  localized_claim_ids?: LocalizedClaimIds;
  schema_version?: SchemaVersion1;
  source_claim_ids?: SourceClaimIds;
}
/**
 * 一次 Claim 层面的变化。reason 供 QA/人工快速判断（漏译/添加事实/否定翻转 等）。
 */
export interface ClaimDelta {
  claim_id?: ClaimId;
  detail: Detail;
  kind: Kind;
  schema_version?: SchemaVersion;
}
