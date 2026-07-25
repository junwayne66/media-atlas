/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AccountId = string;
export type AgeHours = number;
export type Median = number | null;
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
export type P25 = number | null;
export type P75 = number | null;
export type SampleCount = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Entries = AccountBaselineEntry[];
export type GeneratedAt = string;
export type PublishPlatform = "TIKTOK" | "DOUYIN";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;

/**
 * 账号基线（多个 age×metric 条目）——账号内相对指标的分母来源（§11）。
 */
export interface AccountBaseline {
  account_id: AccountId;
  entries?: Entries;
  generated_at: GeneratedAt;
  platform: PublishPlatform;
  schema_version?: SchemaVersion1;
}
/**
 * 账号在某 (age, metric) 下的基线统计（中位数/分位数/样本数）。样本为空时统计为 null。
 */
export interface AccountBaselineEntry {
  age_hours: AgeHours;
  median?: Median;
  metric: MetricField;
  p25?: P25;
  p75?: P75;
  sample_count: SampleCount;
  schema_version?: SchemaVersion;
}
