/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 发生位置（源时间）
 */
export type AtMs = number;
export type Detail = string;
/**
 * 连续性处理（docs/modules/42 §4.2）。
 */
export type ContinuityRuleKind = "J_CUT" | "L_CUT" | "INSERT_BROLL" | "JUMPCUT_SMOOTH" | "BEAT_ALIGN";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Continuity = ContinuityNote[];
export type CreatedAt = string;
export type Id = string;
/**
 * 保留段总时长（输出时长）
 */
export type KeptDurationMs = number;
export type Id1 = string;
/**
 * 原片重剪操作（docs/modules/42 §4.1）。
 */
export type EditOpKind = "KEEP" | "DELETE" | "MUTE" | "SPEED" | "REFRAME";
/**
 * KEEP 在输出中的次序（重排）
 */
export type OutputOrder = number | null;
/**
 * DELETE 原因，如 silence/filler/repeat
 */
export type Reason = string | null;
/**
 * 重构图跟随目标（docs/modules/42 §4.1）。
 */
export type ReframeFollow = "SPEAKER" | "PRODUCT" | "UI" | "FACE" | "CENTER";
export type SafeArea = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 如 9:16
 */
export type TargetAspectRatio = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
/**
 * 覆盖的源转录句段
 */
export type SegmentIds = string[];
export type SourceEndMs = number;
export type SourceStartMs = number;
/**
 * SPEED 倍率
 */
export type Speed = number | null;
export type Ops = EditOp[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
export type SourceAssetId = string | null;
export type SourceTranscriptId = string | null;

/**
 * 原片重剪计划（docs/modules/42 §4）：有序操作 + 连续性说明 + 输出总时长。
 */
export interface ReeditPlan {
  continuity?: Continuity;
  created_at: CreatedAt;
  id: Id;
  kept_duration_ms: KeptDurationMs;
  ops?: Ops;
  schema_version?: SchemaVersion3;
  source_asset_id?: SourceAssetId;
  source_transcript_id?: SourceTranscriptId;
}
/**
 * 连续性处理说明（docs/modules/42 §4.2）。
 */
export interface ContinuityNote {
  at_ms: AtMs;
  detail: Detail;
  kind: ContinuityRuleKind;
  schema_version?: SchemaVersion;
}
/**
 * 一次重剪操作，作用于源时间区间（docs/modules/42 §4.1）。
 */
export interface EditOp {
  id: Id1;
  op: EditOpKind;
  output_order?: OutputOrder;
  reason?: Reason;
  reframe?: ReframeHint | null;
  schema_version?: SchemaVersion2;
  segment_ids?: SegmentIds;
  source_end_ms: SourceEndMs;
  source_start_ms: SourceStartMs;
  speed?: Speed;
}
/**
 * 重构图建议（docs/modules/42 §4.1）。
 */
export interface ReframeHint {
  follow?: ReframeFollow;
  safe_area?: SafeArea;
  schema_version?: SchemaVersion1;
  target_aspect_ratio: TargetAspectRatio;
}
