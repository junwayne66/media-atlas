/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AgeHours = number;
export type AssociationOnly = boolean;
export type EnoughSamples = boolean;
export type Label = string;
export type MedianRelative = number | null;
export type SampleCount = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Buckets = SignalBucketStat[];
export type Correlation = number | null;
/**
 * 信号与相对表现的关联方向（**相关**，非因果）。
 */
export type SignalDirection = "POSITIVE" | "NEGATIVE" | "NONE" | "INSUFFICIENT";
export type EnoughSamples1 = boolean;
/**
 * §10 指标字段名——用于连接器上报"我这个数据源能提供哪些字段"。
 */
export type MetricField =
  | "VIEWS"
  | "WATCH_TIME"
  | "AVG_WATCH_TIME"
  | "COMPLETION_RATE"
  | "LIKES"
  | "COMMENTS"
  | "SHARES"
  | "SAVES"
  | "FOLLOWS"
  | "IMPRESSIONS"
  | "CLICK_THROUGH_RATE";
export type Note = string;
export type SampleCount1 = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * §11 可分析的过程信号。
 */
export type SignalKind =
  | "QA_WARNING_COUNT"
  | "MANUAL_EDIT_COUNT"
  | "HUMAN_SELECTED"
  | "REJECTED_THEN_REVISED"
  | "TREND_HOTNESS"
  | "PUBLISH_DELAY"
  | "DURATION"
  | "HAS_MUSIC";

/**
 * 一个信号对某 (age, metric) 相对结局的关联分析结果。
 *
 * `correlation` 是 Spearman 秩相关 ∈[-1,1]（透明可复现）；`direction` 由相关度 + 阈值 +
 * 样本量得出；`association_only` 恒 True——**关联非因果**（§11 红线）。
 */
export interface LearningSignalResult {
  age_hours: AgeHours;
  association_only?: AssociationOnly;
  buckets?: Buckets;
  correlation?: Correlation;
  direction: SignalDirection;
  enough_samples: EnoughSamples1;
  metric: MetricField;
  note?: Note;
  sample_count: SampleCount1;
  schema_version?: SchemaVersion1;
  signal: SignalKind;
}
/**
 * 按信号值分桶后，该桶内的相对表现统计。
 */
export interface SignalBucketStat {
  enough_samples: EnoughSamples;
  label: Label;
  median_relative?: MedianRelative;
  sample_count: SampleCount;
  schema_version?: SchemaVersion;
}
