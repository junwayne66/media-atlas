/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type MaxErrorRate = number;
export type MaxRecentFatal = number;
export type MinApprovedRenders = number;
export type RecentWindow = number;
export type RequireOwnerApproval = boolean;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type TemplateTrustLevel = "NEW" | "TRUSTED";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type ApprovedRenderCount = number;
export type DuplicatePublishOk = boolean;
export type OwnerApproved = boolean;
export type PublishSuccessOk = boolean;
export type QaMeetsStandard = boolean;
export type RecentErrorRate = number;
export type RecentFatalCount = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type TemplateId = string;
export type TemplateVersion = number;
export type UpdatedAt = string;

/**
 * 模板受信状态机的当前状态（§12）。
 */
export interface TemplateTrustState {
  criteria?: TemplateTrustCriteria;
  level: TemplateTrustLevel;
  schema_version?: SchemaVersion1;
  stats: TemplateTrustStats;
  template_id: TemplateId;
  template_version: TemplateVersion;
  updated_at: UpdatedAt;
}
/**
 * §12 NEW → TRUSTED 升级阈值（可配）。
 */
export interface TemplateTrustCriteria {
  max_error_rate?: MaxErrorRate;
  max_recent_fatal?: MaxRecentFatal;
  min_approved_renders?: MinApprovedRenders;
  recent_window?: RecentWindow;
  require_owner_approval?: RequireOwnerApproval;
  schema_version?: SchemaVersion;
}
/**
 * 模板当前观测统计（§12 升级依据；均为已知事实，不猜）。
 */
export interface TemplateTrustStats {
  approved_render_count: ApprovedRenderCount;
  duplicate_publish_ok: DuplicatePublishOk;
  owner_approved: OwnerApproved;
  publish_success_ok: PublishSuccessOk;
  qa_meets_standard: QaMeetsStandard;
  recent_error_rate: RecentErrorRate;
  recent_fatal_count: RecentFatalCount;
  schema_version?: SchemaVersion2;
}
