/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 会话/凭据留存位置（§8）。
 */
export type AccountBinding = "SERVER_ENCRYPTED" | "DESKTOP" | "DEVICE";
/**
 * §3 发布连接器优先级阶梯。
 */
export type PublishMethod =
  "OFFICIAL_API" | "OFFICIAL_SHARE_SDK" | "BROWSER_AUTOMATION" | "ANDROID_DEVICE" | "MANUAL_EXPORT";
export type ConnectorPreferences = PublishMethod[];
/**
 * 加密 Secret 存储的不透明 Handle——**绝不是** token/password 本体
 */
export type CredentialRef = string;
export type DeviceBindingId = string | null;
export type DisplayName = string;
export type ExternalAccountId = string;
export type Id = string;
export type LastVerifiedAt = string | null;
export type Locale = string;
export type PublishPlatform = "TIKTOK" | "DOUYIN";
export type PublishingWindow = string | null;
export type ReviewPolicyId = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type AccountStatus = "ACTIVE" | "RESTRICTED" | "SUSPENDED" | "UNKNOWN";

/**
 * 一个平台账号（§8）——**只存 handle，不存 secret**。
 */
export interface PlatformAccount {
  binding?: AccountBinding;
  connector_preferences?: ConnectorPreferences;
  credential_ref: CredentialRef;
  device_binding_id?: DeviceBindingId;
  display_name: DisplayName;
  external_account_id: ExternalAccountId;
  id: Id;
  last_verified_at?: LastVerifiedAt;
  locale: Locale;
  platform: PublishPlatform;
  publishing_window?: PublishingWindow;
  review_policy_id?: ReviewPolicyId;
  schema_version?: SchemaVersion;
  status?: AccountStatus;
}
