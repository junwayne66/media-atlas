/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type AccountId = string;
export type At = string;
export type Attempt = number;
export type Detail = string | null;
/**
 * 已提交发帖的外部令牌；有值即视为已提交，用于幂等对账
 */
export type ExternalPostToken = string | null;
export type ExternalUploadToken = string | null;
export type RequestDigest = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Attempts = PublishAttempt[];
export type ContentFingerprint = string | null;
export type CreatedAt = string;
export type ExternalPostId = string | null;
export type ExternalUrl = string | null;
export type Id = string;
export type IdempotencyKey = string;
export type MetadataDigest = string;
/**
 * §3 发布连接器优先级阶梯。
 */
export type PublishMethod =
  "OFFICIAL_API" | "OFFICIAL_SHARE_SDK" | "BROWSER_AUTOMATION" | "ANDROID_DEVICE" | "MANUAL_EXPORT";
export type PublishPlatform = "TIKTOK" | "DOUYIN";
export type RenderDigest = string;
/**
 * 计划窗口标识（如 ISO 时间或 'immediate'）
 */
export type ScheduledWindow = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * §4 发布状态机的状态。
 */
export type PublishState =
  | "PENDING"
  | "PREFLIGHT_BLOCKED"
  | "AWAITING_AUTH"
  | "UPLOADING"
  | "SUBMITTED"
  | "VERIFYING"
  | "SUCCEEDED"
  | "SUCCEEDED_RECONCILED"
  | "FAILED"
  | "WAITING_FOR_HUMAN";
export type UpdatedAt = string;

/**
 * 一个幂等发布任务（§4/§5）。同 idempotency_key 只应存在一个 Job。
 */
export interface PublishJob {
  account_id: AccountId;
  attempts?: Attempts;
  content_fingerprint?: ContentFingerprint;
  created_at: CreatedAt;
  external_post_id?: ExternalPostId;
  external_url?: ExternalUrl;
  id: Id;
  idempotency_key: IdempotencyKey;
  metadata_digest: MetadataDigest;
  method: PublishMethod;
  platform: PublishPlatform;
  render_digest: RenderDigest;
  scheduled_window: ScheduledWindow;
  schema_version?: SchemaVersion1;
  state: PublishState;
  updated_at: UpdatedAt;
}
/**
 * 一次平台调用尝试（§5：每次保存请求摘要 + 外部 upload/post token）。
 */
export interface PublishAttempt {
  at: At;
  attempt: Attempt;
  detail?: Detail;
  external_post_token?: ExternalPostToken;
  external_upload_token?: ExternalUploadToken;
  request_digest: RequestDigest;
  schema_version?: SchemaVersion;
}
