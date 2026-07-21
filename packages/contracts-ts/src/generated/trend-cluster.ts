/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CanonicalTopic = string;
export type CreatedAt = string;
export type EmbeddingRef = string | null;
export type Entities = string[];
export type FirstSeenAt = string;
export type HotScore = number | null;
export type Id = string;
export type Keywords = string[];
export type LastSeenAt = string;
/**
 * 成员 item 引用
 */
export type MemberItemIds = string[];
/**
 * 可解释理由码（40 §10 ≥2）
 */
export type ReasonCodes = string[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SnapshotIds = string[];
export type SourceConfidence = number;
/**
 * 趋势阶段状态机（docs/modules/40-trend-intelligence.md §6）。
 */
export type TrendStage = "EMERGING" | "RISING" | "PEAK" | "SATURATED" | "DECAYING" | "ARCHIVED";
export type Acceleration = number;
export type CrossPlatformScore = number;
export type Decay = number;
export type EngagementEfficiency = number;
export type Novelty = number;
export type Saturation = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type SourceQuality = number;
export type TopicFit = number;
export type Velocity = number;
export type Title = string;
export type UpdatedAt = string;
/**
 * 乐观并发；人工拆分/合并后不被无条件覆盖
 */
export type Version = number;
/**
 * 内容方向，如 ai-tech
 */
export type Vertical = string | null;
/**
 * 算 hot_score 用的权重模板版本
 */
export type WeightsVersion = string | null;

/**
 * 跨平台/跨语言同事件信号聚类（docs/architecture/31 §1.1）。
 *
 * 可版本化聚合：人工拆分/合并产生新版本，member_item_ids 与合并理由保留。
 */
export interface TrendCluster {
  canonical_topic: CanonicalTopic;
  created_at: CreatedAt;
  embedding_ref?: EmbeddingRef;
  entities?: Entities;
  first_seen_at: FirstSeenAt;
  hot_score?: HotScore;
  id: Id;
  keywords?: Keywords;
  last_seen_at: LastSeenAt;
  member_item_ids?: MemberItemIds;
  reason_codes?: ReasonCodes;
  schema_version?: SchemaVersion;
  snapshot_ids?: SnapshotIds;
  source_confidence?: SourceConfidence;
  stage?: TrendStage;
  sub_scores?: TrendSubScores | null;
  title: Title;
  updated_at: UpdatedAt;
  version?: Version;
  vertical?: Vertical;
  weights_version?: WeightsVersion;
}
/**
 * 归一化到 [0,1] 的子分数（40 §5）。velocity/acceleration/engagement/decay
 * 由快照序列算出；其余由聚类上下文/外部信号提供。
 */
export interface TrendSubScores {
  acceleration: Acceleration;
  cross_platform_score?: CrossPlatformScore;
  decay?: Decay;
  engagement_efficiency: EngagementEfficiency;
  novelty?: Novelty;
  saturation?: Saturation;
  schema_version?: SchemaVersion1;
  source_quality?: SourceQuality;
  topic_fit?: TopicFit;
  velocity: Velocity;
}
