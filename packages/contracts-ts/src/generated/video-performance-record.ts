/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AccountId = string;
/**
 * 两种二创模式（docs/architecture/31 §5）。
 */
export type CreationMode = "STRUCTURE_REWRITE" | "SOURCE_REEDIT";
export type DurationMs = number | null;
export type HasMusic = boolean | null;
export type HookKind = string | null;
export type HumanSelected = boolean | null;
export type Language = string | null;
export type ManualEditCount = number | null;
export type PublishDelayHours = number | null;
export type PublishHour = number | null;
export type PublishWeekday = number | null;
export type QaWarningCount = number | null;
export type RejectedThenRevised = boolean | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SubtitleStyle = string | null;
export type TemplateId = string | null;
export type TrendClusterId = string | null;
export type TrendHotnessAtPublish = number | null;
export type VoiceRef = string | null;
export type Id = string;
export type PublishPlatform = "TIKTOK" | "DOUYIN";
export type PublishedAt = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type AccountId1 = string;
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
export type Id1 = string;
export type Impressions = number | null;
export type Likes = number | null;
export type ObservedAt = string;
export type PlatformPostId = string;
export type Saves = number | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type Shares = number | null;
export type SourceConfidence = number;
export type Views = number | null;
/**
 * 总观看时长
 */
export type WatchTimeMs = number | null;
export type Snapshots = PerformanceSnapshot[];

/**
 * 一条已发布视频的归因事实：特征 + 抓到的表现快照（§10/§11 的输入事实，不可变）。
 */
export interface VideoPerformanceRecord {
  account_id: AccountId;
  features: PerformanceFeatures;
  id: Id;
  platform: PublishPlatform;
  published_at: PublishedAt;
  schema_version?: SchemaVersion1;
  snapshots?: Snapshots;
}
/**
 * 一条已发布视频的归因特征（§11）。分组维度相关字段；缺失(None)的维度该视频不计入该分组。
 */
export interface PerformanceFeatures {
  creation_mode?: CreationMode | null;
  duration_ms?: DurationMs;
  has_music?: HasMusic;
  hook_kind?: HookKind;
  human_selected?: HumanSelected;
  language?: Language;
  manual_edit_count?: ManualEditCount;
  publish_delay_hours?: PublishDelayHours;
  publish_hour?: PublishHour;
  publish_weekday?: PublishWeekday;
  qa_warning_count?: QaWarningCount;
  rejected_then_revised?: RejectedThenRevised;
  schema_version?: SchemaVersion;
  subtitle_style?: SubtitleStyle;
  template_id?: TemplateId;
  trend_cluster_id?: TrendClusterId;
  trend_hotness_at_publish?: TrendHotnessAtPublish;
  voice_ref?: VoiceRef;
}
/**
 * §10 表现快照。**每个指标字段缺失保持 null，绝不填 0**（红线）。
 *
 * 非指标元数据（platform/post_id/account/observed_at/age/source_confidence）是必填事实；
 * 只有平台"实际提供的表现指标"才 Optional——它们的 null 表示"平台没给这个数"，
 * 下游统计/归因必须把 null 当作"未知"跳过，永远不能当 0。
 */
export interface PerformanceSnapshot {
  account_id: AccountId1;
  age_hours: AgeHours;
  avg_watch_time_ms?: AvgWatchTimeMs;
  click_through_rate?: ClickThroughRate;
  comments?: Comments;
  completion_rate?: CompletionRate;
  follows?: Follows;
  id: Id1;
  impressions?: Impressions;
  likes?: Likes;
  observed_at: ObservedAt;
  platform: PublishPlatform;
  platform_post_id: PlatformPostId;
  saves?: Saves;
  schema_version?: SchemaVersion2;
  shares?: Shares;
  source_confidence: SourceConfidence;
  views?: Views;
  watch_time_ms?: WatchTimeMs;
}
