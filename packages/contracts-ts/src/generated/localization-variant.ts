/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CanonicalScriptId = string;
export type CreatedAt = string;
export type GlossaryId = string | null;
export type Id = string;
export type Provider = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type CanonicalSentenceId = string;
export type ClaimIds = string[];
/**
 * Claim 的来源核验状态（docs/modules/41 §10.1）。
 */
export type ClaimSourceStatus = "VERIFIED" | "UNVERIFIED" | "DISPUTED" | "OPINION";
export type DurationEstimateMs = number;
export type Id1 = string;
export type NeedsReview = boolean;
export type ReviewReasons = string[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type SemanticSimilarity = number;
export type TargetLanguage = string;
export type Text = string;
export type TraResultId = string | null;
export type Sentences = LocalizedSentence[];
export type TargetLanguage1 = string;
export type TotalDurationEstimateMs = number | null;

/**
 * 一个目标语言的本地化产物：共享 Canonical + Glossary，含逐句 LocalizedSentence。
 */
export interface LocalizationVariant {
  canonical_script_id: CanonicalScriptId;
  created_at: CreatedAt;
  glossary_id?: GlossaryId;
  id: Id;
  provider: Provider;
  schema_version?: SchemaVersion;
  sentences?: Sentences;
  target_language: TargetLanguage1;
  total_duration_estimate_ms?: TotalDurationEstimateMs;
}
/**
 * 派生的本地化句：绑到 CanonicalSentence，承载译文 + 引用的 Claim（可能被 diff 变更）。
 *
 * `needs_review` 由 domain.validate_localization 决定（Claim diff 非空、术语失守、
 * 低相似度、超时长预算等触发）；provider 层不直接置 True。
 */
export interface LocalizedSentence {
  canonical_sentence_id: CanonicalSentenceId;
  claim_ids?: ClaimIds;
  claim_source_status?: ClaimSourceStatus;
  duration_estimate_ms: DurationEstimateMs;
  id: Id1;
  needs_review?: NeedsReview;
  review_reasons?: ReviewReasons;
  schema_version?: SchemaVersion1;
  semantic_similarity: SemanticSimilarity;
  target_language: TargetLanguage;
  text: Text;
  tra_result_id?: TraResultId;
}
