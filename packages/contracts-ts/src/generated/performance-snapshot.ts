/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AccountId = string;
/**
 * 发布至观测时的小时数（可为小数）
 */
export type AgeHours = number;
/**
 * 平均观看时长
 */
export type AvgWatchTimeMs = number | null;
export type ClickThroughRate = number | null;
export type Comments = number | null;
export type CompletionRate = number | null;
export type Follows = number | null;
export type Id = string;
export type Impressions = number | null;
export type Likes = number | null;
export type ObservedAt = string;
export type PublishPlatform = "TIKTOK" | "DOUYIN";
export type PlatformPostId = string;
export type Saves = number | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Shares = number | null;
export type SourceConfidence = number;
export type Views = number | null;
/**
 * 总观看时长
 */
export type WatchTimeMs = number | null;

/**
 * §10 表现快照。**每个指标字段缺失保持 null，绝不填 0**（红线）。
 *
 * 非指标元数据（platform/post_id/account/observed_at/age/source_confidence）是必填事实；
 * 只有平台"实际提供的表现指标"才 Optional——它们的 null 表示"平台没给这个数"，
 * 下游统计/归因必须把 null 当作"未知"跳过，永远不能当 0。
 */
export interface PerformanceSnapshot {
  account_id: AccountId;
  age_hours: AgeHours;
  avg_watch_time_ms?: AvgWatchTimeMs;
  click_through_rate?: ClickThroughRate;
  comments?: Comments;
  completion_rate?: CompletionRate;
  follows?: Follows;
  id: Id;
  impressions?: Impressions;
  likes?: Likes;
  observed_at: ObservedAt;
  platform: PublishPlatform;
  platform_post_id: PlatformPostId;
  saves?: Saves;
  schema_version?: SchemaVersion;
  shares?: Shares;
  source_confidence: SourceConfidence;
  views?: Views;
  watch_time_ms?: WatchTimeMs;
}
