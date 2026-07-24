/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 说话人授权同意书引用；CLONED 必填
 */
export type ConsentRef = string | null;
export type CreatedAt = string;
export type DisplayName = string;
/**
 * 授权到期时间（可选）
 */
export type ExpiresAt = string | null;
export type Id = string;
/**
 * 主语言，如 zh-CN；跨语言由 provider 处理
 */
export type Language = string;
/**
 * Voice Profile 授权状态。**只有 AUTHORIZED 可用于合成**。
 */
export type VoiceLicenseStatus = "AUTHORIZED" | "PENDING" | "DENIED" | "UNCONFIRMED" | "EXPIRED";
export type Notes = string | null;
/**
 * provider 分层（供路由用）。云端最高质，系统最低但预览便宜。
 */
export type TTSProviderTier = "CLOUD_HIGH_QUALITY" | "SELF_HOSTED" | "SYSTEM_PREVIEW";
/**
 * provider 侧的具体 voice id（云端/自托管返回值）
 */
export type ProviderVoiceId = string | null;
/**
 * 原始采样来源引用（artifact id / URL）；CLONED 必填
 */
export type SampleSourceRef = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * 声音种类。
 */
export type VoiceKind = "CLONED" | "PRESET" | "SYSTEM";

/**
 * 一个可复用的声音配置文件。
 *
 * `voice_kind=CLONED` 必须有 `sample_source_ref`（原始采样来源引用）+ `consent_ref`
 * （说话人同意书引用）；否则合同层拒（§7 硬红线）。`license_status=AUTHORIZED` 是使用
 * 合成的**必要**条件——合同层与 provider 层双检；expiration 到期后 provider 应刷新到
 * EXPIRED（合同层不能自动判断时间）。
 */
export interface VoiceProfile {
  consent_ref?: ConsentRef;
  created_at: CreatedAt;
  display_name: DisplayName;
  expires_at?: ExpiresAt;
  id: Id;
  language: Language;
  license_status?: VoiceLicenseStatus;
  notes?: Notes;
  provider_tier?: TTSProviderTier;
  provider_voice_id?: ProviderVoiceId;
  sample_source_ref?: SampleSourceRef;
  schema_version?: SchemaVersion;
  voice_kind: VoiceKind;
}
