/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 参考视频的 VideoBlueprint
 */
export type BlueprintId = string | null;
export type CreatedAt = string;
export type Id = string;
/**
 * 为何是机会（热点证据/角度空白等）
 */
export type Rationale = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SourceAssetIds = string[];
export type TargetLanguage = string;
export type TargetPlatform = string;
export type TrendClusterId = string | null;
export type Vertical = string | null;

/**
 * 一次二创机会：热点聚类 + 源蓝图 + 为何值得做（M04 输入）。
 */
export interface CreativeOpportunity {
  blueprint_id?: BlueprintId;
  created_at: CreatedAt;
  id: Id;
  rationale: Rationale;
  schema_version?: SchemaVersion;
  source_asset_ids?: SourceAssetIds;
  target_language: TargetLanguage;
  target_platform: TargetPlatform;
  trend_cluster_id?: TrendClusterId;
  vertical?: Vertical;
}
