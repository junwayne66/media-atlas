/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 下载连接器名，如 download.f2
 */
export type Connector = string;
/**
 * AcquisitionErrorCode 值
 */
export type ErrorCode = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * DownloadStatus 值，如 unconfigured
 */
export type Status = string;
export type Attempts = AcquisitionAttemptSummary[];
/**
 * 链耗尽 → 应转手工导入
 */
export type ManualFallback = boolean;
export type OutputSha256 = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 最终/路由使用的工具或连接器名
 */
export type ToolName = string;
/**
 * 工具版本；未配置时为 null
 */
export type ToolVersion = string | null;
export type ArtifactIds = string[];
export type CanonicalUrl = string | null;
export type ContentId = string | null;
export type CreatedAt = string;
export type DiscoveredAt = string | null;
/**
 * 素材当前处置。四态互斥，且都能对用户解释「下一步做什么」。
 */
export type SourceDisposition = "IMPORTED" | "MANUAL_FALLBACK" | "NEEDS_EXPANSION" | "UNRESOLVABLE" | "METADATA_ONLY";
/**
 * 失败/未配置时的结构化错误码
 */
export type ErrorCode1 = string | null;
export type FileSha256 = string | null;
export type Id = string;
export type SourceAssetKind = "URL" | "LOCAL_FILE";
export type LastSeenAt = string | null;
export type LocalPath = string | null;
/**
 * 用户粘贴的原文/路径，保留 provenance
 */
export type OriginalInput = string;
/**
 * douyin/tiktok/youtube/manual/unknown
 */
export type Platform = string;
export type ProjectIds = string[];
export type AuthorName = string | null;
export type AuthorPlatformId = string | null;
export type CoverUrl = string | null;
export type Description = string | null;
export type DurationMs = number | null;
export type PublishedAt = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type Title = string | null;
/**
 * 处置理由（面向人的可解释说明）
 */
export type Reason = string;
export type RightsAttestationIds = string[];
export type RightsBasis = "UNKNOWN" | "OWNED" | "LICENSED" | "USER_PROVIDED" | "INTERNAL_APPROVED";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
export type UpdatedAt = string;
/**
 * 乐观并发版本
 */
export type Version = number;

/**
 * 来源素材聚合（可版本化：version 乐观锁）。
 */
export interface SourceAsset {
  acquisition?: AcquisitionSummary | null;
  artifact_ids?: ArtifactIds;
  canonical_url?: CanonicalUrl;
  content_id?: ContentId;
  created_at: CreatedAt;
  discovered_at?: DiscoveredAt;
  disposition: SourceDisposition;
  error_code?: ErrorCode1;
  file_sha256?: FileSha256;
  id: Id;
  kind: SourceAssetKind;
  last_seen_at?: LastSeenAt;
  local_path?: LocalPath;
  original_input: OriginalInput;
  platform?: Platform;
  project_ids?: ProjectIds;
  public_metadata?: SourcePublicMetadata | null;
  reason: Reason;
  rights_attestation_ids?: RightsAttestationIds;
  rights_basis?: RightsBasis;
  schema_version?: SchemaVersion3;
  updated_at: UpdatedAt;
  version?: Version;
}
/**
 * 获取过程的可重放摘要（README §4：工具版本 + 输出哈希 + 可解释尝试轨迹）。
 */
export interface AcquisitionSummary {
  attempts?: Attempts;
  manual_fallback?: ManualFallback;
  output_sha256?: OutputSha256;
  schema_version?: SchemaVersion1;
  tool_name: ToolName;
  tool_version?: ToolVersion;
}
/**
 * 一次下载尝试的摘要（DownloadRouter attempts 轨迹的持久化形态）。
 *
 * 只留「谁试了、结果如何」——不存下载器的原始元数据，更不可能带 Cookie/Token。
 */
export interface AcquisitionAttemptSummary {
  connector: Connector;
  error_code?: ErrorCode;
  schema_version?: SchemaVersion;
  status: Status;
}
export interface SourcePublicMetadata {
  author_name?: AuthorName;
  author_platform_id?: AuthorPlatformId;
  cover_url?: CoverUrl;
  description?: Description;
  duration_ms?: DurationMs;
  published_at?: PublishedAt;
  raw_metadata?: RawMetadata;
  schema_version?: SchemaVersion2;
  stats?: Stats;
  title?: Title;
}
export interface RawMetadata {
  [k: string]: unknown;
}
export interface Stats {
  [k: string]: unknown;
}
