/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type PreflightCheck =
  | "RESOLUTION"
  | "ASPECT_RATIO"
  | "VIDEO_CODEC"
  | "AUDIO_CODEC"
  | "CONTAINER"
  | "FILE_SIZE"
  | "DURATION"
  | "TITLE_LENGTH"
  | "TITLE_BANNED_CHARS"
  | "DESCRIPTION_LENGTH"
  | "TAG_COUNT"
  | "TAG_LENGTH"
  | "AUTH_STATUS"
  | "REVIEW_STATUS"
  | "ACCOUNT_STATUS"
  | "METHOD_UNAVAILABLE";
export type Detail = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * §2 审核/发布严重级别（区别于 VF-309 QA 的 BLOCKER/MAJOR/MINOR/INFO 尺度）。
 */
export type ReviewSeverity = "INFO" | "WARNING" | "ERROR" | "FATAL";
export type Findings = PreflightFinding[];
export type Id = string;
/**
 * §3 发布连接器优先级阶梯。
 */
export type PublishMethod =
  "OFFICIAL_API" | "OFFICIAL_SHARE_SDK" | "BROWSER_AUTOMATION" | "ANDROID_DEVICE" | "MANUAL_EXPORT";
export type PublishPlatform = "TIKTOK" | "DOUYIN";
export type Publishable = boolean;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;

/**
 * 发布前检查报告。`publishable` 必须由 domain 计算；交叉校验拒绝 publishable=True
 * 与任何 ERROR/FATAL 发现并存（手工报告骗不过发布前门）。
 */
export interface PreflightReport {
  created_at: CreatedAt;
  findings?: Findings;
  id: Id;
  method: PublishMethod;
  platform: PublishPlatform;
  publishable: Publishable;
  schema_version?: SchemaVersion1;
}
export interface PreflightFinding {
  check: PreflightCheck;
  detail: Detail;
  evidence?: Evidence;
  schema_version?: SchemaVersion;
  severity: ReviewSeverity;
}
export interface Evidence {
  [k: string]: unknown;
}
