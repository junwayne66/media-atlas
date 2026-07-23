/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type Id = string;
export type AssetId = string;
/**
 * 是否 fallback 兜底（非命中）
 */
export type IsFallback = boolean;
/**
 * 授权/持有方
 */
export type Holder = string;
export type Notes = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * 素材许可类型（每个 ResolvedAsset 必带来源与许可以便追溯）。
 */
export type AssetLicenseType =
  "OWNED" | "LICENSED_STOCK" | "ROYALTY_FREE" | "PUBLIC_DOMAIN" | "GENERATED_MODEL" | "PLACEHOLDER";
/**
 * 到期时间，缺省=不限
 */
export type ValidUntil = string | null;
export type MatchScore = number;
/**
 * 来源提供方标识
 */
export type Provider = string | null;
/**
 * 定位到该素材使用的检索词
 */
export type Query = string;
/**
 * 累计被使用次数（供复用惩罚追踪）
 */
export type ReuseCount = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 所属 AssetPlanSlot
 */
export type SlotId = string;
/**
 * 素材来源层级（docs/modules/42 §6.2 Resolver 顺序）。
 */
export type AssetSource = "SOURCE" | "OWN_LIBRARY" | "STOCK" | "GENERATED" | "PLACEHOLDER";
/**
 * 素材在输出时间线上的使用终点
 */
export type UsageEndMs = number;
/**
 * 素材在输出时间线上的使用起点
 */
export type UsageStartMs = number;
/**
 * 按 slot_id 一对一，缺失=未解析（人工兜底）
 */
export type Resolved = ResolvedAsset[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
/**
 * 允许的来源；未列出者不得选中（合规约束）
 *
 * @minItems 1
 */
export type AllowedSources = [AssetSource, ...AssetSource[]];
/**
 * 如 9:16 / 1:1 / 16:9
 */
export type AspectRatio = string;
/**
 * 如 center / bottom_third
 */
export type SafeArea = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
export type EndMs = number;
/**
 * 素材在时间线上的角色（docs/modules/42 §6.1）。
 */
export type AssetRole =
  "TALKING_HEAD" | "SCREEN_DEMO" | "B_ROLL" | "INFO_CARD" | "LOGO" | "CHART" | "LOWER_THIRD" | "PLACEHOLDER";
/**
 * 语义检索词
 */
export type Query1 = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion4 = string;
export type SemanticRequirements = string[];
export type SlotId1 = string;
export type StartMs = number;
export type Slots = AssetPlanSlot[];
export type SourceTranscriptId = string | null;
export type WeightsVersion = string | null;

/**
 * 聚合：所有槽位 + 解析结果映射。
 */
export interface AssetPlan {
  created_at: CreatedAt;
  id: Id;
  resolved?: Resolved;
  schema_version?: SchemaVersion2;
  slots?: Slots;
  source_transcript_id?: SourceTranscriptId;
  weights_version?: WeightsVersion;
}
/**
 * 一次解析结果：谁、从哪、什么许可、按什么检索词、用在哪段（§6.2 可溯性四要素）。
 */
export interface ResolvedAsset {
  asset_id: AssetId;
  is_fallback?: IsFallback;
  license: AssetLicense;
  match_score: MatchScore;
  provider?: Provider;
  query: Query;
  reuse_count?: ReuseCount;
  schema_version?: SchemaVersion1;
  slot_id: SlotId;
  source: AssetSource;
  usage_end_ms: UsageEndMs;
  usage_start_ms: UsageStartMs;
}
/**
 * 素材许可（合规审计核心；每个 ResolvedAsset 必带）。
 */
export interface AssetLicense {
  holder: Holder;
  notes?: Notes;
  schema_version?: SchemaVersion;
  type: AssetLicenseType;
  valid_until?: ValidUntil;
}
/**
 * 时间线上的一段素材需求（docs/modules/42 §6.1）。
 */
export interface AssetPlanSlot {
  allowed_sources: AllowedSources;
  composition: CompositionSpec;
  end_ms: EndMs;
  /**
   * 全部来源命中失败时的兜底角色
   */
  fallback?: AssetRole | null;
  query: Query1;
  role: AssetRole;
  schema_version?: SchemaVersion4;
  semantic_requirements?: SemanticRequirements;
  slot_id: SlotId1;
  start_ms: StartMs;
}
/**
 * 构图约束（docs/modules/42 §6.1）：目标画幅 + 安全区。
 */
export interface CompositionSpec {
  aspect_ratio: AspectRatio;
  safe_area: SafeArea;
  schema_version?: SchemaVersion3;
}
