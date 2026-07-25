/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AccountId = string;
export type AgeHours = number;
export type AgeHours1 = number;
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
export type GeneratedAt = string;
export type AgeHours2 = number;
/**
 * §11 分组维度。
 */
export type GroupDimension = "TEMPLATE" | "HOOK" | "CREATION_MODE" | "DURATION_BUCKET" | "LANGUAGE" | "PUBLISH_DAYPART";
export type EnoughSamples = boolean;
export type MedianRelative = number | null;
export type P25Relative = number | null;
export type P75Relative = number | null;
export type SampleCount1 = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type Value = string;
export type GroupStats = PerformanceGroupStat[];
export type MinSamples = number;
export type PublishPlatform = "TIKTOK" | "DOUYIN";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;

/**
 * 一个账号在某 (age, metric) 视角下的效果看板：账号基线 + 各维度分组的相对表现。
 *
 * 交叉校验：`median_relative` 非空的分组必须有可用的账号基线中位数（否则相对值无从谈起）。
 */
export interface PerformanceDashboard {
  account_id: AccountId;
  age_hours: AgeHours;
  baseline: AccountBaselineEntry;
  generated_at: GeneratedAt;
  group_stats?: GroupStats;
  metric: MetricField;
  min_samples: MinSamples;
  platform: PublishPlatform;
  schema_version?: SchemaVersion2;
}
/**
 * 账号在某 (age, metric) 下的基线统计（中位数/分位数/样本数）。样本为空时统计为 null。
 */
export interface AccountBaselineEntry {
  age_hours: AgeHours1;
  median?: Median;
  metric: MetricField;
  p25?: P25;
  p75?: P75;
  sample_count: SampleCount;
  schema_version?: SchemaVersion;
}
/**
 * 某分组（维度=值）在某 (age, metric) 下的**账号内相对指标**统计。
 *
 * `median_relative` 是组内各视频 `指标/账号基线中位数` 的中位数；`sample_count` 是参与统计的
 * （相对值非空）视频数；`enough_samples` 标记是否达到可排序/可信阈值。
 */
export interface PerformanceGroupStat {
  age_hours: AgeHours2;
  dimension: GroupDimension;
  enough_samples: EnoughSamples;
  median_relative?: MedianRelative;
  metric: MetricField;
  p25_relative?: P25Relative;
  p75_relative?: P75Relative;
  sample_count: SampleCount1;
  schema_version?: SchemaVersion1;
  value: Value;
}
