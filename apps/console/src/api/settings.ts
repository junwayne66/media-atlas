/**
 * M-W10 本地安全设置 API。
 *
 * 响应类型结构上没有 secret/credential_ref；敏感请求对象只在表单提交栈中短暂创建，
 * 不进入 store、URL 或浏览器持久化。
 */
import { api } from "./client";

export type VaultState = "UNINITIALIZED" | "LOCKED" | "UNLOCKED";
export type ProviderKind = "LLM" | "ASR" | "VLM";
export type CredentialAction = "KEEP" | "REPLACE" | "CLEAR";
export type Platform = "DOUYIN" | "TIKTOK";
export type AccountAuthMethod =
  | "OFFICIAL_API"
  | "BROWSER_AUTOMATION"
  | "ANDROID_DEVICE"
  | "MANUAL_EXPORT";
export type AccountBinding = "SERVER_ENCRYPTED" | "DESKTOP" | "DEVICE";

export interface VaultView {
  state: VaultState;
  initialized: boolean;
  unlocked: boolean;
}

export interface ProviderView {
  kind: ProviderKind;
  provider_name: string;
  model_name: string | null;
  base_url: string | null;
  enabled: boolean;
  options: Record<string, unknown>;
  credential_configured: boolean;
  readiness: "DISABLED" | "MISSING_CREDENTIAL" | "CONFIGURED_UNVERIFIED";
  row_version: number;
  created_at: string;
  updated_at: string;
}

export interface PlatformAccountView {
  id: string;
  platform: Platform;
  display_name: string;
  external_account_id: string;
  auth_method: AccountAuthMethod;
  binding: AccountBinding;
  locale: string;
  publishing_window: string | null;
  enabled: boolean;
  credential_configured: boolean;
  verification_status: "UNVERIFIED";
  row_version: number;
  created_at: string;
  updated_at: string;
}

export interface SettingsSnapshot {
  vault: VaultView;
  providers: ProviderView[];
  accounts: PlatformAccountView[];
  live_connections_enabled: false;
}

export interface SecretBundleInput {
  api_key?: string;
  access_token?: string;
  refresh_token?: string;
  client_secret?: string;
}

export interface ProviderWriteInput {
  provider_name: string;
  model_name: string | null;
  base_url: string | null;
  enabled: boolean;
  options: Record<string, unknown>;
  expected_version: number | null;
  credential_action: CredentialAction;
  credential?: SecretBundleInput;
}

export interface AccountWriteInput {
  platform: Platform;
  display_name: string;
  external_account_id: string;
  auth_method: AccountAuthMethod;
  binding: AccountBinding;
  locale: string;
  publishing_window: string | null;
  enabled: boolean;
  expected_version: number | null;
  credential_action: CredentialAction;
  credential?: SecretBundleInput;
  external_credential_ref?: string;
}

export function getSettings(): Promise<SettingsSnapshot> {
  return api.get<SettingsSnapshot>("/v1/settings");
}

export function initializeVault(passphrase: string): Promise<VaultView> {
  return api.post<VaultView>("/v1/settings/vault:initialize", {
    passphrase,
    confirmation: passphrase,
  });
}

export function unlockVault(passphrase: string): Promise<VaultView> {
  return api.post<VaultView>("/v1/settings/vault:unlock", { passphrase });
}

export function lockVault(): Promise<VaultView> {
  return api.post<VaultView>("/v1/settings/vault:lock");
}

export function saveProvider(
  kind: ProviderKind,
  body: ProviderWriteInput,
): Promise<ProviderView> {
  return api.put<ProviderView>(`/v1/settings/providers/${kind}`, body);
}

export function removeProvider(kind: ProviderKind, expectedVersion: number): Promise<void> {
  return api.delete<void>(`/v1/settings/providers/${kind}`, {
    expected_version: expectedVersion,
  });
}

export function createAccount(body: AccountWriteInput): Promise<PlatformAccountView> {
  return api.post<PlatformAccountView>("/v1/settings/accounts", body);
}

export function saveAccount(
  accountId: string,
  body: AccountWriteInput,
): Promise<PlatformAccountView> {
  return api.put<PlatformAccountView>(
    `/v1/settings/accounts/${encodeURIComponent(accountId)}`,
    body,
  );
}

export function removeAccount(accountId: string, expectedVersion: number): Promise<void> {
  return api.delete<void>(`/v1/settings/accounts/${encodeURIComponent(accountId)}`, {
    expected_version: expectedVersion,
  });
}
