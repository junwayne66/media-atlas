/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
/**
 * §12 语言 QA 自动检查项。
 */
export type LocalizationQACheck =
  | "CLAIM_CONSISTENCY"
  | "NUMBER_CONSISTENCY"
  | "PROPER_NOUN_CONSISTENCY"
  | "NEGATION_CONSISTENCY"
  | "GLOSSARY"
  | "PRONUNCIATION"
  | "UNTRANSLATED_TEXT"
  | "SUBTITLE_LINE_LENGTH"
  | "SUBTITLE_READING_SPEED"
  | "SUBTITLE_OVERLAP"
  | "SUBTITLE_SAFE_AREA"
  | "TTS_GAP"
  | "TTS_REPEAT"
  | "TTS_TRUNCATION"
  | "TTS_LEVEL"
  | "TTS_CLIP"
  | "DURATION_EXCEEDED"
  | "EXTREME_SPEED"
  | "LIPSYNC_SYNC"
  | "AV_SYNC";
export type Detail = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SentenceId = string;
/**
 * QA 严重级（docs/modules/42 §11）。BLOCKER 一处即拒；MAJOR 超阈升级；MINOR/INFO 记录。
 */
export type QASeverity = "BLOCKER" | "MAJOR" | "MINOR" | "INFO";
export type Findings = LocalizationQAFinding[];
export type Id = string;
export type LocalizationVariantId = string;
export type PassOrBlock = boolean;
export type ReviewedSentenceIds = string[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;

/**
 * 一个 LocalizationVariant 的语言 QA 报告。
 *
 * `pass_or_block` 必须由 domain 的发布门计算；合同层交叉校验拒绝
 * `pass_or_block=True` 与任何 BLOCKER 并存——手工构造的报告骗不过门。
 */
export interface LocalizationQAReport {
  created_at: CreatedAt;
  findings?: Findings;
  id: Id;
  localization_variant_id: LocalizationVariantId;
  pass_or_block: PassOrBlock;
  reviewed_sentence_ids?: ReviewedSentenceIds;
  schema_version?: SchemaVersion1;
}
/**
 * 一条逐句 QA 发现。
 */
export interface LocalizationQAFinding {
  check: LocalizationQACheck;
  detail: Detail;
  evidence?: Evidence;
  schema_version?: SchemaVersion;
  sentence_id: SentenceId;
  severity: QASeverity;
}
export interface Evidence {
  [k: string]: unknown;
}
