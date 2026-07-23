/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
/**
 * 发生时刻（输出时间线）
 */
export type AtMs = number;
/**
 * 可读描述
 */
export type Detail = string | null;
/**
 * 持续时长；0 表示瞬时事件
 */
export type DurationMs = number;
export type Id = string;
/**
 * QA 检测项（docs/modules/42 §11）。覆盖视频/音频/字幕/合规四大类。
 */
export type QAFindingKind =
  | "BLACK_FRAME"
  | "FROZEN_FRAME"
  | "FLICKER"
  | "DUPLICATE_FRAMES"
  | "HOLE"
  | "VOICE_TAIL_CUT"
  | "ABRUPT_SILENCE"
  | "LOUDNESS_OUT_OF_RANGE"
  | "TRUE_PEAK_CLIP"
  | "CAPTION_OFF_SAFE_AREA"
  | "CAPTION_OVERLAP"
  | "BROLL_RATIO_LOW"
  | "SUBJECT_CUT"
  | "UI_CROP"
  | "CLEANUP_FLICKER"
  | "DURATION_MISMATCH";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * QA 严重级（docs/modules/42 §11）。BLOCKER 一处即拒；MAJOR 超阈升级；MINOR/INFO 记录。
 */
export type QASeverity = "BLOCKER" | "MAJOR" | "MINOR" | "INFO";
/**
 * 所属轨道 id，如 v1/a0/v4
 */
export type TrackRef = string | null;
export type Findings = QAFinding[];
export type Id1 = string;
/**
 * 渲染成品实测总时长（ffprobe）
 */
export type MeasuredDurationMs = number;
export type PassOrBlock = boolean;
/**
 * §11 关联 RenderManifest
 */
export type RenderManifestId = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * Timeline 声明的总时长
 */
export type TimelineDurationMs = number;
export type TimelineId = string;

/**
 * 一次渲染的 QA 报告：全部发现 + 时长一致性 + 发布门结论。
 */
export interface QAReport {
  created_at: CreatedAt;
  findings?: Findings;
  id: Id1;
  measured_duration_ms: MeasuredDurationMs;
  pass_or_block?: PassOrBlock;
  render_manifest_id?: RenderManifestId;
  schema_version?: SchemaVersion1;
  timeline_duration_ms: TimelineDurationMs;
  timeline_id: TimelineId;
}
/**
 * 单条 QA 发现：位置 + 类别 + 严重级 + 证据键值对。
 */
export interface QAFinding {
  at_ms: AtMs;
  detail?: Detail;
  duration_ms?: DurationMs;
  evidence?: Evidence;
  id: Id;
  kind: QAFindingKind;
  schema_version?: SchemaVersion;
  severity: QASeverity;
  track_ref?: TrackRef;
}
/**
 * 度量证据，如 {mean_luma: 3.2, threshold: 8}
 */
export interface Evidence {
  [k: string]: string | number | boolean;
}
