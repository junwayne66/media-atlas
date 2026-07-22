/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type Id = string;
export type OcrProvider = string;
export type OcrVersion = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SourceArtifactId = string | null;
export type Confidence = number;
export type EndMs = number;
export type Id1 = string;
/**
 * 文本轨类型（docs/modules/41 §8）。区分字幕/标题/UI/品牌水印/场景文字。
 */
export type TextTrackKind = "CAPTION" | "TITLE" | "LOWER_THIRD" | "UI" | "SCENE_TEXT" | "BRAND_MARK" | "UNKNOWN";
export type LowConfidence = boolean;
/**
 * STATIC / MOVING
 */
export type Motion = string | null;
export type H = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type W = number;
export type X = number;
export type Y = number;
export type Confidence1 = number;
export type FrameTimeMs = number;
export type Occluded = boolean;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type Text = string;
/**
 * 逐帧轨迹
 */
export type Observations = TextObservation[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
export type SourceArtifactId1 = string | null;
export type StartMs = number;
export type StyleHint = string | null;
/**
 * 多帧投票后的规范文本
 */
export type Text1 = string;
export type Tracks = TextTrack[];

/**
 * 一次 OCR 分析产出的全部文本轨（顶层可持久化/交换合同）。
 */
export interface TextTrackSet {
  created_at: CreatedAt;
  id: Id;
  ocr_provider: OcrProvider;
  ocr_version?: OcrVersion;
  schema_version?: SchemaVersion;
  source_artifact_id?: SourceArtifactId;
  tracks?: Tracks;
}
/**
 * 跨帧聚合的稳定文本轨（41 §8.6：时间范围、bbox、遮挡、运动、置信度、样式提示）。
 */
export interface TextTrack {
  confidence: Confidence;
  end_ms: EndMs;
  id: Id1;
  kind?: TextTrackKind;
  low_confidence?: LowConfidence;
  motion?: Motion;
  observations?: Observations;
  schema_version?: SchemaVersion3;
  source_artifact_id?: SourceArtifactId1;
  start_ms: StartMs;
  style_hint?: StyleHint;
  text: Text1;
}
/**
 * 单帧文本检测（OCR 原始输出，也是 TextTrack 的轨迹点）。
 */
export interface TextObservation {
  bbox: BBox;
  confidence: Confidence1;
  frame_time_ms: FrameTimeMs;
  occluded?: Occluded;
  schema_version?: SchemaVersion2;
  text: Text;
}
/**
 * 归一化边界框（原点左上，x 向右、y 向下）。四边形退化为轴对齐框（MVP）。
 */
export interface BBox {
  h: H;
  schema_version?: SchemaVersion1;
  w: W;
  x: X;
  y: Y;
}
