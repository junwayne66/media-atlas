/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type Angle = string;
export type Audience = string;
/**
 * 禁用：照抄标题/未证实结论等
 */
export type Avoid = string[];
export type BlueprintId = string | null;
export type ClaimTableId = string | null;
export type CreatedAt = string;
/**
 * 两种二创模式（docs/architecture/31 §5）。
 */
export type CreationMode = "STRUCTURE_REWRITE" | "SOURCE_REEDIT";
export type Cta = string | null;
export type DurationTargetMs = number;
/**
 * 给观众的承诺
 */
export type Promise = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * 如 counter_intuitive_claim
 */
export type Type = string;
export type Id = string;
/**
 * 必须覆盖的 Claim
 */
export type MustCoverClaimIds = string[];
export type Objective = string;
export type OpportunityId = string | null;
export type Platform = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type TargetLanguage = string;
export type Broll = number;
export type InfoCard = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type ScreenDemo = number;
export type TalkingHead = number;

/**
 * 创意简报（docs/modules/42 §2）。必须引用热点证据/Claims。
 */
export interface CreativeBrief {
  angle: Angle;
  audience: Audience;
  avoid?: Avoid;
  blueprint_id?: BlueprintId;
  claim_table_id?: ClaimTableId;
  created_at: CreatedAt;
  creation_mode: CreationMode;
  cta?: Cta;
  duration_target_ms: DurationTargetMs;
  hook?: BriefHook | null;
  id: Id;
  must_cover_claim_ids?: MustCoverClaimIds;
  objective: Objective;
  opportunity_id?: OpportunityId;
  platform: Platform;
  schema_version?: SchemaVersion1;
  target_language: TargetLanguage;
  visual_mix?: VisualMix | null;
}
/**
 * 开场钩子。
 */
export interface BriefHook {
  promise: Promise;
  schema_version?: SchemaVersion;
  type: Type;
}
/**
 * 视觉配比（docs/modules/42 §2）。四类占比之和应 ≈ 1。
 */
export interface VisualMix {
  broll?: Broll;
  info_card?: InfoCard;
  schema_version?: SchemaVersion2;
  screen_demo?: ScreenDemo;
  talking_head?: TalkingHead;
}
