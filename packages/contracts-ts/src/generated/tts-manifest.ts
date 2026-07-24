/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 合成音频 artifact id；FAILED/UNCONFIGURED 时为 None
 */
export type AudioArtifactId = string | null;
export type CreatedAt = string;
export type DurationMs = number | null;
export type Id = string;
export type Language = string;
export type Provider = string;
/**
 * provider 分层（供路由用）。云端最高质，系统最低但预览便宜。
 */
export type TTSProviderTier = "CLOUD_HIGH_QUALITY" | "SELF_HOSTED" | "SYSTEM_PREVIEW";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Seed = number | null;
/**
 * 源脚本句 id 或翻译句 id
 */
export type SentenceId = string;
/**
 * 实际使用的语速倍数（time fit 后）
 */
export type SpeedUsed = number | null;
/**
 * input text+config 的哈希
 */
export type TextHash = string;
export type ToolVersion = string | null;
export type VoiceProfileId = string;
export type Confidence = number | null;
export type EndMs = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type StartMs = number;
export type Text = string;
export type WordTimings = TTSWordTiming[];

/**
 * 一次 TTS 合成的可重放 manifest（同 41 §11 精神：input digest + provider +
 * tool_version + config → activity cache key）。
 *
 * input_text_hash 就是本次合成文本 + 语言 + voice_profile_id + style + target_duration
 * + lexicon_id + seed 的组合哈希；由 domain 侧算出。
 */
export interface TTSManifest {
  audio_artifact_id?: AudioArtifactId;
  created_at: CreatedAt;
  duration_ms?: DurationMs;
  id: Id;
  language: Language;
  provider: Provider;
  provider_tier: TTSProviderTier;
  schema_version?: SchemaVersion;
  seed?: Seed;
  sentence_id: SentenceId;
  speed_used?: SpeedUsed;
  text_hash: TextHash;
  tool_version?: ToolVersion;
  voice_profile_id: VoiceProfileId;
  word_timings?: WordTimings;
}
/**
 * 合成后的词级时间；跟 VF-402 SubtitleWord 不同——TTS 直接产 word onset，不
 * 需 forced alignment。confidence 通常来自 provider 内部对齐质量估计。
 */
export interface TTSWordTiming {
  confidence?: Confidence;
  end_ms: EndMs;
  schema_version?: SchemaVersion1;
  start_ms: StartMs;
  text: Text;
}
