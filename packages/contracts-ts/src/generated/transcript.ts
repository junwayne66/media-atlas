/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type DurationMs = number | null;
/**
 * 注入的热词（产品名/人名），用于中文热点词偏置
 */
export type Hotwords = string[];
export type Id = string;
/**
 * 主语言；混语时各段带自身 language
 */
export type Language = string;
export type AlignVersion = string | null;
/**
 * 如 medium / large-v3
 */
export type AsrModel = string | null;
/**
 * 如 asr.whisper_cpp / asr.whisperx
 */
export type AsrProvider = string;
export type AsrVersion = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SpeakerVersion = string | null;
export type VadVersion = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type Confidence = number;
export type EndMs = number;
export type Id1 = string;
/**
 * BCP-47，如 zh-CN / en-US
 */
export type Language1 = string;
export type LowConfidence = boolean;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
/**
 * 说话人聚类 id，如 spk_0
 */
export type SpeakerId = string | null;
export type StartMs = number;
export type Text = string;
export type Confidence1 = number;
export type EndMs1 = number;
export type LowConfidence1 = boolean;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
export type StartMs1 = number;
export type Text1 = string;
export type Words = TranscriptWord[];
export type Segments = TranscriptSegment[];
/**
 * 源音频/视频 Artifact
 */
export type SourceArtifactId = string | null;

/**
 * 一次转录的统一产出（词级合同）。段内可含不同语言（混语）。
 */
export interface Transcript {
  created_at: CreatedAt;
  duration_ms?: DurationMs;
  hotwords?: Hotwords;
  id: Id;
  language: Language;
  models: TranscriptModels;
  schema_version?: SchemaVersion1;
  segments?: Segments;
  source_artifact_id?: SourceArtifactId;
}
/**
 * 可重放：ASR/VAD/对齐/说话人模型与版本（41 §7.2「保存 VAD、对齐和说话人模型版本」）。
 */
export interface TranscriptModels {
  align_version?: AlignVersion;
  asr_model?: AsrModel;
  asr_provider: AsrProvider;
  asr_version?: AsrVersion;
  schema_version?: SchemaVersion;
  speaker_version?: SpeakerVersion;
  vad_version?: VadVersion;
}
/**
 * 段级转录（一个说话片段）。混语时按段带各自 language（41 §7.1）。
 */
export interface TranscriptSegment {
  confidence: Confidence;
  end_ms: EndMs;
  id: Id1;
  language: Language1;
  low_confidence?: LowConfidence;
  schema_version?: SchemaVersion2;
  speaker_id?: SpeakerId;
  start_ms: StartMs;
  text: Text;
  words?: Words;
}
/**
 * 词级时间与置信度。低置信词进入审核标记（41 §7.2）。
 */
export interface TranscriptWord {
  confidence: Confidence1;
  end_ms: EndMs1;
  low_confidence?: LowConfidence1;
  schema_version?: SchemaVersion3;
  start_ms: StartMs1;
  text: Text1;
}
