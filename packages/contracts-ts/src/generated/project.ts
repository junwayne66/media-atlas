/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 预算策略引用；超限时进入 WAITING_FOR_BUDGET_APPROVAL
 */
export type BudgetPolicy = string | null;
export type ChannelProfileId = string | null;
export type CreatedAt = string;
/**
 * 两种二创模式（docs/architecture/31 §5）。
 */
export type CreationMode = "STRUCTURE_REWRITE" | "SOURCE_REEDIT";
/**
 * 任务路由策略（docs/architecture/30 §6）。
 */
export type ExecutionPolicy = "LOCAL_ONLY" | "LOCAL_PREFERRED" | "CLOUD_PREFERRED" | "CLOUD_ONLY";
/**
 * UUIDv7/ULID，外部不可枚举
 */
export type Id = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SourceAssetIds = string[];
/**
 * BCP-47，如 zh-CN
 */
export type SourceLanguage = string;
/**
 * Project 状态机（docs/architecture/31 §3）。FAILED 不是删除。
 */
export type ProjectStatus =
  | "DRAFT"
  | "INGESTING"
  | "ANALYZING"
  | "PLANNING"
  | "EDITING"
  | "LOCALIZING"
  | "QC"
  | "REVIEW"
  | "APPROVED"
  | "PUBLISHING"
  | "WAITING_FOR_HUMAN"
  | "PUBLISHED"
  | "MEASURING"
  | "COMPLETED"
  | "FAILED";
/**
 * BCP-47 列表
 *
 * @minItems 1
 */
export type TargetLanguages = [string, ...string[]];
export type TemplateVersionId = string | null;
export type Title = string;
/**
 * 来源热点聚类
 */
export type TrendClusterId = string | null;
export type UpdatedAt = string;
/**
 * 内容方向，如 ai-tech
 */
export type Vertical = string;
/**
 * Temporal workflow id
 */
export type WorkflowId = string | null;

/**
 * 一条创作任务的业务根（docs/architecture/31 §1.2）。
 */
export interface Project {
  budget_policy?: BudgetPolicy;
  channel_profile_id?: ChannelProfileId;
  created_at: CreatedAt;
  creation_mode: CreationMode;
  execution_policy?: ExecutionPolicy;
  id: Id;
  schema_version?: SchemaVersion;
  source_asset_ids?: SourceAssetIds;
  source_language: SourceLanguage;
  status?: ProjectStatus;
  target_languages: TargetLanguages;
  template_version_id?: TemplateVersionId;
  title: Title;
  trend_cluster_id?: TrendClusterId;
  updated_at: UpdatedAt;
  vertical: Vertical;
  workflow_id?: WorkflowId;
}
