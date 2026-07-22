/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
/**
 * VLM 描述；null=尚未分析
 */
export type Caption = string | null;
export type Confidence = number | null;
export type FrameTimeMs = number;
/**
 * VLM 标签：人物/屏录/产品/图卡等
 */
export type Labels = string[];
/**
 * 被选中的原因（可多个）
 *
 * @minItems 1
 */
export type Reasons = [FrameSampleReason, ...FrameSampleReason[]];
/**
 * 代表帧被选中的原因（docs/modules/41 §9）。VLM 只分析代表帧，禁逐帧。
 */
export type FrameSampleReason =
  "KEYFRAME" | "SCENE_CUT" | "TEXT_CHANGE" | "SPEAKER_CHANGE" | "LOW_CONFIDENCE" | "PERIODIC";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Frames = FrameAnalysis[];
export type Id = string;
/**
 * 选帧策略标识，如 representative@v1
 */
export type SamplingPolicy = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type SourceArtifactId = string | null;
/**
 * null=仅选帧未分析
 */
export type VlmProvider = string | null;
export type VlmVersion = string | null;

/**
 * 一次视觉分析：代表帧集 + （可选）VLM provider/版本 + 采样策略。可重放。
 */
export interface VisualAnalysis {
  created_at: CreatedAt;
  frames?: Frames;
  id: Id;
  sampling_policy: SamplingPolicy;
  schema_version?: SchemaVersion1;
  source_artifact_id?: SourceArtifactId;
  vlm_provider?: VlmProvider;
  vlm_version?: VlmVersion;
}
/**
 * 一帧代表帧：为何被选 + （分析后的）VLM 输出。
 */
export interface FrameAnalysis {
  caption?: Caption;
  confidence?: Confidence;
  frame_time_ms: FrameTimeMs;
  labels?: Labels;
  reasons: Reasons;
  schema_version?: SchemaVersion;
}
