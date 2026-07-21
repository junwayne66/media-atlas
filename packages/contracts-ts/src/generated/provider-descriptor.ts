/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * @minItems 1
 */
export type Capabilities = [string, ...string[]];
export type Currency = string;
export type EstimatedCostPerUnit = number | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * 计费单位，如 second / 1k_tokens / request
 */
export type Unit = string;
/**
 * 默认执行位置
 */
export type ExecutionLocation = string;
export type LastError = string | null;
export type LastSuccessAt = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type HealthState = "healthy" | "degraded" | "down" | "unknown";
/**
 * 许可证/接口隔离等级（docs/20-open-source-landscape.md §3）。
 */
export type IsolationLevel = "L0" | "L1" | "L2" | "L3" | "L4";
/**
 * 支持语言，BCP-47
 */
export type Languages = string[];
/**
 * 代码/模型/权重许可证要点；来源 third_party_manifest.yaml
 */
export type LicenseNotes = string | null;
/**
 * 唯一名，如 asr.whisper-cpp
 */
export type Name = string;
/**
 * 适用平台，如 douyin/tiktok
 */
export type Platforms = string[];
/**
 * Provider 类型全集（docs/10-module-overview.md §4）。
 */
export type ProviderType =
  | "SourceConnector"
  | "DownloadProvider"
  | "ASRProvider"
  | "OCRProvider"
  | "LLMProvider"
  | "VLMProvider"
  | "TTSProvider"
  | "LipSyncProvider"
  | "StockMediaProvider"
  | "GenerativeMediaProvider"
  | "RenderProvider"
  | "TimelineExporter"
  | "PublishConnector"
  | "MetricsConnector";
/**
 * 所需 Secret 的名称（非值）
 */
export type RequiredSecrets = string[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type Version = string;

/**
 * Provider 注册描述（docs/10-module-overview.md §4 必声明字段）。
 */
export interface ProviderDescriptor {
  capabilities: Capabilities;
  cost_model?: CostModel | null;
  execution_location: ExecutionLocation;
  health?: ProviderHealth;
  isolation_level?: IsolationLevel;
  languages?: Languages;
  license_notes?: LicenseNotes;
  name: Name;
  platforms?: Platforms;
  provider_type: ProviderType;
  required_secrets?: RequiredSecrets;
  schema_version?: SchemaVersion2;
  version: Version;
}
export interface CostModel {
  currency?: Currency;
  estimated_cost_per_unit?: EstimatedCostPerUnit;
  schema_version?: SchemaVersion;
  unit: Unit;
}
export interface ProviderHealth {
  last_error?: LastError;
  last_success_at?: LastSuccessAt;
  schema_version?: SchemaVersion1;
  status?: HealthState;
}
