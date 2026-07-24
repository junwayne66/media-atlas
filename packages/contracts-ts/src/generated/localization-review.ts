/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
/**
 * EDITED 时的新译文；其它状态必须为 None
 */
export type EditedText = string | null;
export type Note = string | null;
export type Reviewer = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SentenceId = string;
/**
 * 句级审核状态（§12 人工界面：批准可针对句子）。
 */
export type ReviewState = "PENDING" | "APPROVED" | "REJECTED" | "EDITED";
export type Decisions = SentenceReviewDecision[];
export type Id = string;
export type LocalizationVariantId = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;

/**
 * 一个 LocalizationVariant 的句级审核集合。
 */
export interface LocalizationReview {
  created_at: CreatedAt;
  decisions?: Decisions;
  id: Id;
  localization_variant_id: LocalizationVariantId;
  schema_version?: SchemaVersion1;
}
/**
 * 对单句的审核决策。EDITED 必须携带 edited_text。
 */
export interface SentenceReviewDecision {
  edited_text?: EditedText;
  note?: Note;
  reviewer?: Reviewer;
  schema_version?: SchemaVersion;
  sentence_id: SentenceId;
  state: ReviewState;
}
