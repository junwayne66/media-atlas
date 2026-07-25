/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AccountId = string;
export type CapturedAgesHours = number[];
export type Id = string;
/**
 * @minItems 1
 */
export type PlannedAgesHours = [number, ...number[]];
export type PublishPlatform = "TIKTOK" | "DOUYIN";
export type PlatformPostId = string;
export type PublishedAt = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;

/**
 * 一个帖子的快照计划（§10 建议 1/3/6/24/72h/7d，按平台限流调整）。
 *
 * `planned_ages_hours` 是计划观测的年龄点（小时）；`captured_ages_hours` 是已抓取的年龄点。
 * domain 据 published_at + now 算"现在该抓哪个/下一个定时器何时触发"。
 */
export interface SnapshotSchedule {
  account_id: AccountId;
  captured_ages_hours?: CapturedAgesHours;
  id: Id;
  planned_ages_hours: PlannedAgesHours;
  platform: PublishPlatform;
  platform_post_id: PlatformPostId;
  published_at: PublishedAt;
  schema_version?: SchemaVersion;
}
