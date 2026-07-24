/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * @minItems 1
 */
export type AllowedAspectRatios = [string, ...string[]];
/**
 * @minItems 1
 */
export type AllowedAudioCodecs = [string, ...string[]];
/**
 * @minItems 1
 */
export type AllowedContainers = [string, ...string[]];
/**
 * @minItems 1
 */
export type AllowedVideoCodecs = [string, ...string[]];
export type BannedTitleChars = string[];
export type DescriptionMaxLen = number;
export type MaxDurationMs = number;
export type MaxFileSizeBytes = number;
export type MaxHeight = number;
export type MaxTags = number;
export type MaxWidth = number;
export type MinDurationMs = number;
export type MinHeight = number;
export type MinWidth = number;
export type PublishPlatform = "TIKTOK" | "DOUYIN";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type TagMaxLen = number;
export type TitleMaxLen = number;

/**
 * 平台发布规则集（数据化 §3.1/§3.2/§9 约束，可按平台/账号覆盖）。
 */
export interface PlatformPublishSpec {
  allowed_aspect_ratios: AllowedAspectRatios;
  allowed_audio_codecs: AllowedAudioCodecs;
  allowed_containers: AllowedContainers;
  allowed_video_codecs: AllowedVideoCodecs;
  banned_title_chars?: BannedTitleChars;
  description_max_len: DescriptionMaxLen;
  max_duration_ms: MaxDurationMs;
  max_file_size_bytes: MaxFileSizeBytes;
  max_height: MaxHeight;
  max_tags: MaxTags;
  max_width: MaxWidth;
  min_duration_ms: MinDurationMs;
  min_height: MinHeight;
  min_width: MinWidth;
  platform: PublishPlatform;
  schema_version?: SchemaVersion;
  tag_max_len: TagMaxLen;
  title_max_len: TitleMaxLen;
}
