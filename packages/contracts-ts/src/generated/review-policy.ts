/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type Id = string;
/**
 * §12 审核策略：何时需要人工审核。
 */
export type ReviewPolicyMode = "ALWAYS" | "NEW_TEMPLATE_ONLY" | "AUTO";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Version = number;
/**
 * WARNING 是否阻塞（模板/账号策略，§2）
 */
export type WarningBlocks = boolean;

/**
 * 审核策略快照（版本化，供 ReviewDecision.policy_snapshot_id 引用）。
 */
export interface ReviewPolicy {
  created_at: CreatedAt;
  id: Id;
  mode: ReviewPolicyMode;
  schema_version?: SchemaVersion;
  version?: Version;
  warning_blocks?: WarningBlocks;
}
