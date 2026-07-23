/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type DurationTargetMs = number;
export type Id = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type EndMs = number;
/**
 * 本节拍应达成的功能（抽象，非原句）
 */
export type Guidance = string | null;
export type Id1 = string;
/**
 * 表达层节拍（docs/modules/41 §10.1）。UNCLASSIFIED 允许存在以保覆盖率。
 */
export type RhetoricalBeatKind =
  "HOOK" | "QUESTION" | "EVIDENCE" | "CONTRAST" | "DEMO" | "CONCLUSION" | "CTA" | "UNCLASSIFIED";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type StartMs = number;
export type TargetDurationMs = number;
export type Slots = BeatSlot[];
export type SourceBlueprintId = string | null;

/**
 * 抽象节拍模板（缩放到目标时长）。只复用节拍功能 + 时长比。
 */
export interface BeatTemplate {
  created_at: CreatedAt;
  duration_target_ms: DurationTargetMs;
  id: Id;
  schema_version?: SchemaVersion;
  slots?: Slots;
  source_blueprint_id?: SourceBlueprintId;
}
/**
 * 节拍槽位：功能 + 目标时长（不含原句）。
 */
export interface BeatSlot {
  end_ms: EndMs;
  guidance?: Guidance;
  id: Id1;
  role: RhetoricalBeatKind;
  schema_version?: SchemaVersion1;
  start_ms: StartMs;
  target_duration_ms: TargetDurationMs;
}
