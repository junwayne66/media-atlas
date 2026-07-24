/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type Notes = string | null;
/**
 * IPA / 拼音 / provider 支持的任何标注（provider 决定语法）
 */
export type Pronunciation = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Surface = string;
export type Entries = PronunciationEntry[];
export type Id = string;
export type Language = string;
/**
 * provider 分层（供路由用）。云端最高质，系统最低但预览便宜。
 */
export type TTSProviderTier = "CLOUD_HIGH_QUALITY" | "SELF_HOSTED" | "SYSTEM_PREVIEW";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type Version = number;

/**
 * 一对（provider, language）的发音词典。entries surface 唯一。
 */
export interface PronunciationLexicon {
  created_at: CreatedAt;
  entries?: Entries;
  id: Id;
  language: Language;
  /**
   * null 表示跨 provider 通用；有值即绑定该层的标注格式
   */
  provider_tier?: TTSProviderTier | null;
  schema_version?: SchemaVersion1;
  version?: Version;
}
/**
 * 发音词典的一条：surface（原文形式）→ ipa / pinyin / hint。
 */
export interface PronunciationEntry {
  notes?: Notes;
  pronunciation: Pronunciation;
  schema_version?: SchemaVersion;
  surface: Surface;
}
