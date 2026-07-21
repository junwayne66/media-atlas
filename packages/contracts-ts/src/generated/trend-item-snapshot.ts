/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AuthorId = string | null;
export type CollectorVersion = string;
export type Comments = number | null;
export type FollowersAtObservation = number | null;
export type HashtagIds = string[];
export type Id = string;
export type ItemId = string;
export type Likes = number | null;
export type Locale = string | null;
export type ObservedAt = string;
export type Platform = string;
export type PublishedAt = string | null;
export type Rank = number | null;
/**
 * 原始响应/页面证据 Artifact
 */
export type RawArtifactId = string | null;
export type Region = string | null;
export type Saves = number | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Shares = number | null;
export type SoundId = string | null;
/**
 * 官方/公开页/抓取/手工导入的可信度（40 §3.2）
 */
export type SourceConfidence = number;
export type Views = number | null;

/**
 * 周期采集的原始平台观测（docs/modules/40 §3.1）。不可变——热度靠序列算。
 *
 * 缺失指标保留 null，绝不填 0（40 §3.2）：区分"真的是 0"与"没采到"。
 */
export interface TrendItemSnapshot {
  author_id?: AuthorId;
  collector_version: CollectorVersion;
  comments?: Comments;
  followers_at_observation?: FollowersAtObservation;
  hashtag_ids?: HashtagIds;
  id: Id;
  item_id: ItemId;
  likes?: Likes;
  locale?: Locale;
  observed_at: ObservedAt;
  platform: Platform;
  published_at?: PublishedAt;
  rank?: Rank;
  raw_artifact_id?: RawArtifactId;
  region?: Region;
  saves?: Saves;
  schema_version?: SchemaVersion;
  shares?: Shares;
  sound_id?: SoundId;
  source_confidence: SourceConfidence;
  views?: Views;
}
