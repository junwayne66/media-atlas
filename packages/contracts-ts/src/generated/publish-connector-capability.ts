/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AccountStatus = "ACTIVE" | "RESTRICTED" | "SUSPENDED" | "UNKNOWN";
export type AuthStatus = "AUTHORIZED" | "PENDING_REVIEW" | "UNAUTHORIZED" | "EXPIRED";
/**
 * 该方法当前是否可用
 */
export type Available = boolean;
/**
 * §3.1 客户端/应用审核状态（未审核 → 可见性受限）。
 */
export type ClientReviewStatus = "APPROVED" | "UNDER_REVIEW" | "UNAUDITED";
export type DirectPost = boolean;
export type MaxFileSizeBytes = number | null;
/**
 * §3 发布连接器优先级阶梯。
 */
export type PublishMethod =
  "OFFICIAL_API" | "OFFICIAL_SHARE_SDK" | "BROWSER_AUTOMATION" | "ANDROID_DEVICE" | "MANUAL_EXPORT";
export type Notes = string | null;
export type PublishPlatform = "TIKTOK" | "DOUYIN";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SupportedContainers = string[];

/**
 * 连接器上报的能力 + 授权/审核/账号状态（§3 "Connector 返回能力，不由 UI 猜"）。
 */
export interface PublishConnectorCapability {
  account_status: AccountStatus;
  auth_status: AuthStatus;
  available: Available;
  client_review_status?: ClientReviewStatus;
  direct_post?: DirectPost;
  max_file_size_bytes?: MaxFileSizeBytes;
  method: PublishMethod;
  notes?: Notes;
  platform: PublishPlatform;
  schema_version?: SchemaVersion;
  supported_containers?: SupportedContainers;
}
