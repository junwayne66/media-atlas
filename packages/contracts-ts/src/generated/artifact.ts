/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 均值哈希（docs/architecture/30 §7）
 */
export type Ahash = string | null;
export type AudioFingerprint = string | null;
export type CreatedAt = string;
export type Filename = string;
/**
 * UUIDv7/ULID
 */
export type Id = string;
/**
 * 如 source_video / proxy / render / analysis
 */
export type Kind = string;
export type Channels = number | null;
export type Codec = string | null;
export type DurationS = number | null;
export type Fps = number | null;
export type Height = number | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * 如 1/30000
 */
export type TimeBase = string | null;
export type Width = number | null;
export type MimeType = string;
/**
 * 视频感知哈希
 */
export type Phash = string | null;
export type Activity = string | null;
export type Model = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type Tool = string | null;
export type ToolVersion = string | null;
export type ProjectId = string | null;
export type RetentionPolicy = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
/**
 * 敏感级别标记
 */
export type Sensitivity = string | null;
export type Sha256 = string;
export type SizeBytes = number;
export type StorageBackend = "s3" | "local_cache";
export type Bucket = string | null;
export type LocalPath = string | null;
export type ObjectKey = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
export type UpstreamArtifactIds = string[];

/**
 * 不可变产物记录（docs/architecture/30 §7）。同哈希可去重，来源记录不得合并丢失。
 */
export interface Artifact {
  ahash?: Ahash;
  audio_fingerprint?: AudioFingerprint;
  created_at: CreatedAt;
  filename: Filename;
  id: Id;
  kind: Kind;
  media?: MediaProbe | null;
  mime_type: MimeType;
  phash?: Phash;
  produced_by?: ProducedBy | null;
  project_id?: ProjectId;
  retention_policy?: RetentionPolicy;
  schema_version?: SchemaVersion2;
  sensitivity?: Sensitivity;
  sha256: Sha256;
  size_bytes: SizeBytes;
  storage: StorageRef;
  upstream_artifact_ids?: UpstreamArtifactIds;
}
/**
 * 探测出的媒体技术属性（可选，非媒体 Artifact 无此段）。
 */
export interface MediaProbe {
  channels?: Channels;
  codec?: Codec;
  duration_s?: DurationS;
  fps?: Fps;
  height?: Height;
  schema_version?: SchemaVersion;
  time_base?: TimeBase;
  width?: Width;
}
/**
 * 生成来源：Activity、工具与模型版本（可重放性要求）。
 */
export interface ProducedBy {
  activity?: Activity;
  model?: Model;
  schema_version?: SchemaVersion1;
  tool?: Tool;
  tool_version?: ToolVersion;
}
/**
 * 存储位置。对象键不承载业务真值（docs/architecture/30 §7）。
 */
export interface StorageRef {
  backend: StorageBackend;
  bucket?: Bucket;
  local_path?: LocalPath;
  object_key?: ObjectKey;
  schema_version?: SchemaVersion3;
}
