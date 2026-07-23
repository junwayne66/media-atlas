/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
/**
 * 每秒计数，须与 timeline 一致
 */
export type Rate = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * 以 rate 为单位的整数计数
 */
export type Value = number;
export type Id = string;
export type ProjectId = string | null;
/**
 * 全 timeline 帧率/采样率基准；所有 track/segment 须一致
 */
export type Rate1 = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type SourceAssetIds = string[];
export type SourceTranscriptId = string | null;
export type Id1 = string;
/**
 * 时间线轨道类型（docs/modules/42 §8.1）。V0..V5 视频层 / A0..A3 音频层 / M0 语义标记。
 */
export type TrackKind =
  | "V0_BACKGROUND"
  | "V1_PRIMARY_VIDEO"
  | "V2_BROLL_SCREEN"
  | "V3_INFO_CARDS"
  | "V4_CAPTIONS"
  | "V5_OVERLAYS"
  | "A0_ORIGINAL"
  | "A1_DUB"
  | "A2_MUSIC"
  | "A3_SFX"
  | "M0_MARKERS";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
/**
 * 智能重构图的裁剪轨迹标识
 */
export type CropPath = string | null;
export type Kind = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
export type Effects = SegmentEffect[];
export type Id2 = string;
export type Language = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion4 = string;
/**
 * passthrough/dub/subtitle_only …
 */
export type Strategy = string;
/**
 * ResolvedAsset.id / Claim.id 等可溯性引用
 */
export type ProvenanceRef = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion5 = string;
export type ScriptSentenceId = string | null;
/**
 * 如 HOOK/EVIDENCE/CTA
 */
export type SemanticRole = string | null;
/**
 * 源素材 asset_id 或占位
 */
export type SourceRef = string | null;
export type SpeakerId = string | null;
export type TemplateSlot = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion6 = string;
export type Segments = Segment[];
export type Tracks = Track[];

/**
 * 领域时间线真值（ADR-003）：rate + 多轨 + 总时长 + 来源引用。
 */
export interface CreativeTimeline {
  created_at: CreatedAt;
  duration: RationalTime;
  id: Id;
  project_id?: ProjectId;
  rate: Rate1;
  schema_version?: SchemaVersion1;
  source_asset_ids?: SourceAssetIds;
  source_transcript_id?: SourceTranscriptId;
  tracks?: Tracks;
}
/**
 * 有理时间（OTIO 兼容）：value/rate 秒。等价性以 value*other.rate == other.value*rate 判定。
 */
export interface RationalTime {
  rate: Rate;
  schema_version?: SchemaVersion;
  value: Value;
}
/**
 * 时间线单轨（docs/modules/42 §8.1）。同轨 segment 不得重叠，由 validate_timeline 检查。
 */
export interface Track {
  id: Id1;
  kind: TrackKind;
  schema_version?: SchemaVersion2;
  segments?: Segments;
}
/**
 * 时间线上的一个片段（docs/modules/42 §8.2）。九扩展字段用于回溯语义、模板、来源、多语言。
 */
export interface Segment {
  crop_path?: CropPath;
  effects?: Effects;
  id: Id2;
  localization?: LocalizationPolicy | null;
  provenance_ref?: ProvenanceRef;
  schema_version?: SchemaVersion5;
  script_sentence_id?: ScriptSentenceId;
  semantic_role?: SemanticRole;
  source_ref?: SourceRef;
  speaker_id?: SpeakerId;
  template_slot?: TemplateSlot;
  time_range: RationalTimeRange;
}
/**
 * 效果占位：具体参数由 Render Graph 阶段消费；此处仅记录 kind + 参数字典。
 */
export interface SegmentEffect {
  kind: Kind;
  params?: Params;
  schema_version?: SchemaVersion3;
}
export interface Params {
  [k: string]: string | number | boolean;
}
/**
 * 本地化策略（多语言版本），标记本 Segment 依赖的语言资源。
 */
export interface LocalizationPolicy {
  language: Language;
  schema_version?: SchemaVersion4;
  strategy?: Strategy;
}
/**
 * 有理时间段 [start, start+duration)。duration 可为 0，表示瞬时点。
 */
export interface RationalTimeRange {
  duration: RationalTime;
  schema_version?: SchemaVersion6;
  start: RationalTime;
}
