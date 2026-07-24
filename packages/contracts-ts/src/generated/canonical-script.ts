/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type Id = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type ScriptVersionId = string | null;
export type BeatSlotId = string;
export type ClaimIds = string[];
/**
 * 允许缩/扩比例（±%），供时长拟合
 */
export type EditFlexibility = number;
export type Id1 = string;
/**
 * 必须保留的术语（引用 Glossary.source_term）
 */
export type MustKeepTerms = string[];
export type PronunciationHints = string[];
/**
 * 表达层节拍（docs/modules/41 §10.1）。UNCLASSIFIED 允许存在以保覆盖率。
 */
export type RhetoricalBeatKind =
  "HOOK" | "QUESTION" | "EVIDENCE" | "CONTRAST" | "DEMO" | "CONCLUSION" | "CTA" | "UNCLASSIFIED";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 本句的功能/意图（抽象，语言无关）
 */
export type SemanticIntent = string;
export type SourceLanguage = string;
export type SourceText = string;
export type SourceTimeRangeEndMs = number;
export type SourceTimeRangeStartMs = number;
export type SpeakerId = string | null;
export type TargetDurationMs = number;
/**
 * 引用同期镜头/文本轨 id
 */
export type VisualDependencies = string[];
export type Sentences = CanonicalSentence[];
export type SourceLanguage1 = string;
export type TotalDurationMs = number | null;

/**
 * 中性稿：单份、语言无关；每目标语言从此派生 LocalizationVariant。
 */
export interface CanonicalScript {
  created_at: CreatedAt;
  id: Id;
  schema_version?: SchemaVersion;
  script_version_id?: ScriptVersionId;
  sentences?: Sentences;
  source_language: SourceLanguage1;
  total_duration_ms?: TotalDurationMs;
}
/**
 * 中性稿的一句：语言无关的语义 + 时长预算 + 引用 Claim + must_keep_terms（§3）。
 *
 * 翻译修改不直接覆盖这里；派生 LocalizedSentence 承载译文。
 */
export interface CanonicalSentence {
  beat_slot_id: BeatSlotId;
  claim_ids?: ClaimIds;
  edit_flexibility?: EditFlexibility;
  id: Id1;
  must_keep_terms?: MustKeepTerms;
  pronunciation_hints?: PronunciationHints;
  role: RhetoricalBeatKind;
  schema_version?: SchemaVersion1;
  semantic_intent: SemanticIntent;
  source_language: SourceLanguage;
  source_text: SourceText;
  source_time_range_end_ms: SourceTimeRangeEndMs;
  source_time_range_start_ms: SourceTimeRangeStartMs;
  speaker_id?: SpeakerId;
  target_duration_ms: TargetDurationMs;
  visual_dependencies?: VisualDependencies;
}
