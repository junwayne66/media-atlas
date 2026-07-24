/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 中文阅读速度上限，字/秒
 */
export type CjkCharsPerSec = number | null;
export type CreatedAt = string;
/**
 * 英文 CPS 上限
 */
export type EnCharsPerSec = number | null;
/**
 * 英文 WPM/60 上限，可选
 */
export type EnWordsPerSec = number | null;
export type Id = string;
/**
 * 模板绑定的字幕语言，如 zh-CN / en-US
 */
export type Language = string;
export type MaxCharsPerLine = number;
export type MaxCueDurationMs = number;
export type MaxLinesPerCue = number;
export type MinCueDurationMs = number;
export type BottomMaxPct = number;
export type LeftMinPct = number;
export type RightMaxPct = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type TopMinPct = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type Bold = boolean;
/**
 * #RRGGBB
 */
export type Color = string | null;
export type FontFamily = string | null;
export type FontSizePt = number | null;
/**
 * #RRGGBB
 */
export type OutlineColor = string | null;
export type OutlineWidth = number | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type Version = number;

/**
 * 字幕模板：分段 + 阅读速度 + 安全区 + 样式（每语言/平台/账号一份，可版本化）。
 *
 * - max_chars_per_line：单行字符上限。中文按字符（含全角），英文按字符（近似 42）。
 *   两语言不同，故建议按 language 建两份模板；此字段配当前 language。
 * - max_lines_per_cue：≤2（§5.1）；短视频默认 1。
 * - cjk_chars_per_sec / en_chars_per_sec / en_words_per_sec：阅读速度上限（软阈值，超即 QA）。
 * - min_cue_duration_ms：单条 cue 最短持续（避免闪现），默认 800ms。
 * - max_cue_duration_ms：单条最长（避免长时间悬挂），默认 6000ms。
 * - safe_area：安全区约束（渲染 + QA 消费）。
 * - style_hint：字体/描边等提示（不承载真实字体渲染）。
 */
export interface SubtitleTemplate {
  cjk_chars_per_sec?: CjkCharsPerSec;
  created_at: CreatedAt;
  en_chars_per_sec?: EnCharsPerSec;
  en_words_per_sec?: EnWordsPerSec;
  id: Id;
  language: Language;
  max_chars_per_line: MaxCharsPerLine;
  max_cue_duration_ms?: MaxCueDurationMs;
  max_lines_per_cue?: MaxLinesPerCue;
  min_cue_duration_ms?: MinCueDurationMs;
  safe_area?: SafeAreaSpec;
  schema_version?: SchemaVersion1;
  style_hint?: SubtitleStyleHint;
  version?: Version;
}
/**
 * 安全区约束（归一化百分比 0-100）；渲染/QA 消费。默认覆盖抖音/TikTok 底部 UI 占位。
 */
export interface SafeAreaSpec {
  bottom_max_pct?: BottomMaxPct;
  left_min_pct?: LeftMinPct;
  right_max_pct?: RightMaxPct;
  schema_version?: SchemaVersion;
  top_min_pct?: TopMinPct;
}
/**
 * 字体样式提示（渲染层参考，不做真实 layout）。
 */
export interface SubtitleStyleHint {
  bold?: Bold;
  color?: Color;
  font_family?: FontFamily;
  font_size_pt?: FontSizePt;
  outline_color?: OutlineColor;
  outline_width?: OutlineWidth;
  schema_version?: SchemaVersion2;
}
