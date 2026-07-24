/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type Notes = string | null;
export type PreserveSource = boolean;
export type Pronunciation = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SourceTerm = string;
export type TargetTerm = string;
export type Entries = GlossaryEntry[];
export type Id = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type SourceLanguage = string;
export type TargetLanguage = string;
export type Version = number;

/**
 * 术语表（一对语言）。entries 里 source_term + source_language + target_language 唯一。
 */
export interface Glossary {
  created_at: CreatedAt;
  entries?: Entries;
  id: Id;
  schema_version?: SchemaVersion1;
  source_language: SourceLanguage;
  target_language: TargetLanguage;
  version?: Version;
}
/**
 * 术语条目：source_term 在目标语言里锁定为 target_term；可选发音提示。
 *
 * - `preserve_source=True`：目标译文里必须原样保留（产品名/模型名 通常如此）；
 *   与 target_term 二选一——preserve_source 时 target_term 强制等于 source_term。
 * - `pronunciation`：给 TTS 参考的读音（IPA/拼音/自然拼写），本身不参与译文替换。
 * - `notes`：给译者/审核的说明（如"缩写读作字母"）。
 */
export interface GlossaryEntry {
  notes?: Notes;
  preserve_source?: PreserveSource;
  pronunciation?: Pronunciation;
  schema_version?: SchemaVersion;
  source_term: SourceTerm;
  target_term: TargetTerm;
}
