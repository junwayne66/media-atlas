/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type MaxDurationMs = number;
/**
 * 允许的最大脸数（单主脸=1）
 */
export type MaxFaces = number;
export type MaxHeadTurnDeg = number;
export type MaxOcclusionRatio = number;
export type MinDurationMs = number;
/**
 * 面部高度 / 画面高度的最小比（太小 → FACE_TOO_SMALL）
 */
export type MinFaceHeightRatio = number;
export type MinSpeakerProbability = number;
export type RequireDubAligned = boolean;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Eligible = boolean;
export type EndMs = number;
/**
 * 一个片段最终的口型处理方式（GPU 合成 + §10.2 回退阶梯）。
 */
export type LipSyncMethod = "GPU_SYNTHESIS" | "ORIGINAL_TAKE" | "BROLL_COVER" | "FASTER_CUT" | "KEEP_UNSYNCED";
/**
 * §10.1 资格不符原因。
 */
export type LipSyncIneligibleReason =
  | "MODE_OFF"
  | "NO_PRIMARY_FACE"
  | "MULTIPLE_FACES"
  | "FACE_TOO_SMALL"
  | "OCCLUSION_HIGH"
  | "LOW_SPEAKER_PROBABILITY"
  | "DURATION_OUT_OF_RANGE"
  | "HEAD_TURN_TOO_LARGE"
  | "DUB_NOT_ALIGNED";
export type IneligibleReasons = LipSyncIneligibleReason[];
export type NeedsReview = boolean;
/**
 * 脸区边界融合
 */
export type BoundaryScore = number;
/**
 * 身份一致（不换脸）
 */
export type IdentityScore = number;
/**
 * 运动/口型自然
 */
export type MotionScore = number;
/**
 * 是否通过 QA（不过则须降级）
 */
export type Passed = boolean;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 肤色一致
 */
export type SkinToneScore = number;
/**
 * 该决策的原因（人可读）
 */
export type Rationale = string;
/**
 * 需人工复核的原因（provider 与 domain 都可能置）。
 */
export type LipSyncReviewReason = "FORCE_REVIEW" | "QA_FAILED" | "SYNTHESIS_FAILED" | "FALLBACK_USED" | "KEPT_UNSYNCED";
export type ReviewReasons = LipSyncReviewReason[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type SegmentId = string;
export type StartMs = number;
/**
 * GPU_SYNTHESIS 成功时的局部脸区产物
 */
export type SynthesizedArtifactId = string | null;
export type Decisions = LipSyncSegmentDecision[];
export type Id = string;
export type LocalizationVariantId = string;
/**
 * §10.2 口型模式。
 */
export type LipSyncMode = "OFF" | "AUTO_ELIGIBLE" | "FORCE_REVIEW";
export type Provider = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;

/**
 * 一次口型同步计划（模式 + 资格阈值 + 逐片段决策）。
 */
export interface LipSyncPlan {
  created_at: CreatedAt;
  criteria?: LipSyncEligibilityCriteria;
  decisions?: Decisions;
  id: Id;
  localization_variant_id: LocalizationVariantId;
  mode: LipSyncMode;
  provider?: Provider;
  schema_version?: SchemaVersion3;
}
/**
 * §10.1 资格阈值（可按模板/模型能力覆盖）。
 */
export interface LipSyncEligibilityCriteria {
  max_duration_ms?: MaxDurationMs;
  max_faces?: MaxFaces;
  max_head_turn_deg?: MaxHeadTurnDeg;
  max_occlusion_ratio?: MaxOcclusionRatio;
  min_duration_ms?: MinDurationMs;
  min_face_height_ratio?: MinFaceHeightRatio;
  min_speaker_probability?: MinSpeakerProbability;
  require_dub_aligned?: RequireDubAligned;
  schema_version?: SchemaVersion;
}
/**
 * 对一个配音片段的口型决策。
 *
 * 不变量（合同层硬拦）：`GPU_SYNTHESIS` 只能用于合格片段；不合格必须记录原因。
 */
export interface LipSyncSegmentDecision {
  eligible: Eligible;
  end_ms: EndMs;
  /**
   * 从哪个方式降级来的（自动降级记录）
   */
  fallback_from?: LipSyncMethod | null;
  ineligible_reasons?: IneligibleReasons;
  method: LipSyncMethod;
  needs_review?: NeedsReview;
  /**
   * GPU_SYNTHESIS 已执行时的 QA 报告
   */
  qa?: LipSyncQAReport | null;
  rationale: Rationale;
  review_reasons?: ReviewReasons;
  schema_version?: SchemaVersion2;
  segment_id: SegmentId;
  start_ms: StartMs;
  synthesized_artifact_id?: SynthesizedArtifactId;
}
/**
 * §10.2 合成后一致性 QA（边界、肤色、运动、身份）。分数 ∈ [0,1]，越高越好。
 */
export interface LipSyncQAReport {
  boundary_score: BoundaryScore;
  identity_score: IdentityScore;
  motion_score: MotionScore;
  passed: Passed;
  schema_version?: SchemaVersion1;
  skin_tone_score: SkinToneScore;
}
