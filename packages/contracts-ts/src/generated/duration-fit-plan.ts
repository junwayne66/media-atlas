/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
/**
 * TTS 估算时长（VF-404 estimate）
 */
export type EstimatedMs = number;
/**
 * 估算/目标；用于最终伸缩记录
 */
export type FinalRatio = number;
/**
 * §8 五步顺序策略。
 */
export type DurationFitStrategy = "LLM_REWRITE" | "TTS_SPEED" | "BROLL_ADJUST" | "TIME_STRETCH" | "BEAT_REPLAN";
export type Rationale = string;
export type ReviewReasons = string[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SentenceId = string;
/**
 * 决策结果状态。
 */
export type DurationFitStatus = "OK_UNCHANGED" | "OK_FITTED" | "NEEDS_REVIEW" | "FAILED";
export type TargetMs = number;
export type Decisions = DurationFitDecision[];
export type Id = string;
export type LocalizationVariantId = string;
export type NaturalSpeedMax = number;
export type NaturalSpeedMin = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 非人脸时间伸缩绝对幅度（±5%）
 */
export type StretchMaxAbsRatio = number;

/**
 * 一整个 LocalizationVariant 的拟合计划。
 */
export interface DurationFitPlan {
  created_at: CreatedAt;
  decisions?: Decisions;
  id: Id;
  localization_variant_id: LocalizationVariantId;
  natural_speed_max?: NaturalSpeedMax;
  natural_speed_min?: NaturalSpeedMin;
  schema_version?: SchemaVersion1;
  stretch_max_abs_ratio?: StretchMaxAbsRatio;
}
/**
 * 一句的拟合决策。fit_method 与 final_ratio 忠实记录（§8 每句必录）。
 */
export interface DurationFitDecision {
  estimated_ms: EstimatedMs;
  final_ratio: FinalRatio;
  /**
   * OK_UNCHANGED 时为 None
   */
  fit_method?: DurationFitStrategy | null;
  rationale: Rationale;
  review_reasons?: ReviewReasons;
  schema_version?: SchemaVersion;
  sentence_id: SentenceId;
  status: DurationFitStatus;
  target_ms: TargetMs;
}
