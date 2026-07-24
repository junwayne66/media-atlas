/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type FrameEndMs = number;
export type FrameStartMs = number;
export type Id = string;
/**
 * AUTHORIZED_INPAINT 的授权凭证引用
 */
export type LicenseRef = string | null;
/**
 * Clean Plate 生成方法（§6.2）。
 */
export type CleanPlateMethod = "BACKGROUND_ESTIMATE" | "AUTHORIZED_INPAINT" | "SKIP";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SourceArtifactId = string;
export type SourceTrackId = string;
export type CleanPlateRequests = CleanPlateRequest[];
export type CreatedAt = string;
/**
 * 策略需要 Clean Plate 时引用其 id
 */
export type CleanPlateRequestId = string | null;
/**
 * 翻译后文本长度 / 源长度；> policy.max 走回退
 */
export type LayoutExpansionRatio = number | null;
export type NeedsReview = boolean;
/**
 * 选择该策略的原因（人可读）
 */
export type Rationale = string;
/**
 * 需人工审核的原因（provider 与 domain 都可能置）。
 */
export type TextLocalizationReviewReason =
  | "LOW_OCR_CONFIDENCE"
  | "OCCLUSION_HIGH"
  | "MOTION_UNSUPPORTED"
  | "LICENSE_UNCONFIRMED"
  | "LAYOUT_OVERFLOW"
  | "CLEAN_PLATE_FAILED"
  | "GLOSSARY_MISS"
  | "UNKNOWN_KIND";
export type ReviewReasons = TextLocalizationReviewReason[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 文本轨类型（docs/modules/41 §8）。区分字幕/标题/UI/品牌水印/场景文字。
 */
export type TextTrackKind = "CAPTION" | "TITLE" | "LOWER_THIRD" | "UI" | "SCENE_TEXT" | "BRAND_MARK" | "UNKNOWN";
export type SourceText = string;
export type SourceTrackId1 = string;
/**
 * 一条 TextTrack 的本地化策略。
 */
export type TextLocalizationStrategy =
  "REDRAW" | "REPLACE_OVERLAY" | "INFO_CARD_FALLBACK" | "KEEP_AS_IS" | "SKIP" | "LOCALIZE_ANNOTATION";
export type TargetLanguage = string;
/**
 * KEEP_AS_IS / SKIP / BRAND_MARK 未授权时可为 None
 */
export type TranslatedText = string | null;
export type Decisions = TextTrackLocalizationDecision[];
export type Id1 = string;
export type PolicyId = string;
export type Provider = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type SourceTextTrackSetId = string;
export type TargetLanguage1 = string;

/**
 * 一次画面文字本地化计划（多轨决策 + Clean Plate 请求集合）。
 */
export interface TextLocalizationPlan {
  clean_plate_requests?: CleanPlateRequests;
  created_at: CreatedAt;
  decisions?: Decisions;
  id: Id1;
  policy_id: PolicyId;
  provider?: Provider;
  schema_version?: SchemaVersion2;
  source_text_track_set_id: SourceTextTrackSetId;
  target_language: TargetLanguage1;
}
/**
 * 一次 Clean Plate 请求（供 provider-sdk CleanPlateProvider 消费）。
 */
export interface CleanPlateRequest {
  frame_end_ms: FrameEndMs;
  frame_start_ms: FrameStartMs;
  id: Id;
  license_ref?: LicenseRef;
  method: CleanPlateMethod;
  schema_version?: SchemaVersion;
  source_artifact_id: SourceArtifactId;
  source_track_id: SourceTrackId;
}
/**
 * 对一条 TextTrack 的本地化决策。
 */
export interface TextTrackLocalizationDecision {
  clean_plate_request_id?: CleanPlateRequestId;
  layout_expansion_ratio?: LayoutExpansionRatio;
  needs_review?: NeedsReview;
  rationale: Rationale;
  review_reasons?: ReviewReasons;
  schema_version?: SchemaVersion1;
  source_kind: TextTrackKind;
  source_text: SourceText;
  source_track_id: SourceTrackId1;
  strategy: TextLocalizationStrategy;
  target_language: TargetLanguage;
  translated_text?: TranslatedText;
}
