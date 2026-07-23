/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type BeatTemplateId = string | null;
export type BriefId = string | null;
export type ClaimTableId = string | null;
export type CreatedAt = string;
export type Id = string;
export type Language = string;
export type RewriteProvider = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type BeatSlotId = string;
/**
 * 本句主张的 Claim 引用
 */
export type ClaimIds = string[];
export type Editable = boolean;
export type Id1 = string;
export type Language1 = string;
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
 * 按语言语速估算，非字符粗算
 */
export type TargetDurationMs = number;
export type Text = string;
export type Sentences = ScriptSentence[];
export type TotalDurationMs = number | null;
export type Version = number;

/**
 * 可逐句编辑的脚本版本（docs/modules/42 §3.2 第 7 步）。
 */
export interface ScriptVersion {
  beat_template_id?: BeatTemplateId;
  brief_id?: BriefId;
  claim_table_id?: ClaimTableId;
  created_at: CreatedAt;
  id: Id;
  language: Language;
  rewrite_provider?: RewriteProvider;
  schema_version?: SchemaVersion;
  sentences?: Sentences;
  total_duration_ms?: TotalDurationMs;
  version?: Version;
}
/**
 * Canonical Script 的一句：中性语义、逐句可编辑，带估算时长与引用 Claim。
 */
export interface ScriptSentence {
  beat_slot_id: BeatSlotId;
  claim_ids?: ClaimIds;
  editable?: Editable;
  id: Id1;
  language: Language1;
  role: RhetoricalBeatKind;
  schema_version?: SchemaVersion1;
  target_duration_ms: TargetDurationMs;
  text: Text;
}
