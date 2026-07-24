/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 被审内容的摘要；内容一改即变 → 旧审批失效
 */
export type ContentDigest = string;
export type CreatedAt = string;
export type ReviewDecisionKind = "APPROVED" | "REJECTED" | "CHANGES_REQUESTED";
export type EntityId = string;
export type EntityVersion = number;
export type Id = string;
export type Note = string | null;
export type PolicySnapshotId = string;
export type QcReportIds = string[];
export type ReviewerId = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * 审批对象的粒度（§1.2）。
 */
export type ReviewScope = "VARIANT" | "PACKAGE" | "TEMPLATE" | "PROJECT";
/**
 * 无密钥内容绑定摘要（见模块 docstring 安全说明）
 */
export type Signature = string;

/**
 * 一次审核决定（§1.2）。绑定到 entity 的具体 version + content_digest。
 */
export interface ReviewDecision {
  content_digest: ContentDigest;
  created_at: CreatedAt;
  decision: ReviewDecisionKind;
  entity_id: EntityId;
  entity_version: EntityVersion;
  id: Id;
  note?: Note;
  policy_snapshot_id: PolicySnapshotId;
  qc_report_ids?: QcReportIds;
  reviewer_id: ReviewerId;
  schema_version?: SchemaVersion;
  scope: ReviewScope;
  signature: Signature;
}
