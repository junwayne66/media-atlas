/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type EndMs = number;
/**
 * 惩罚项：越高越依赖上下文
 */
export type ContextDependency = number;
export type EmotionalEnergy = number;
export type EndingPayoff = number;
export type HookStrength = number;
export type InformationDensity = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type SelfContainedness = number;
export type SpeakerProminence = number;
export type SurpriseOrConflict = number;
/**
 * 惩罚项：越高技术瑕疵越重
 */
export type TechnicalDefect = number;
export type TopicRelevance = number;
export type VisualActivity = number;
/**
 * 人工对候选的处置（docs/modules/42 §5.3）。选中/放弃原因成为训练标签。
 */
export type HighlightLabel = "UNREVIEWED" | "SELECTED" | "REJECTED";
/**
 * 人工选中/放弃原因 → 训练标签
 */
export type HumanLabelReason = string | null;
export type Id = string;
/**
 * 校准项，无训练数据时为 null，不伪装预测
 */
export type PredictedRetention = number | null;
/**
 * 热门片段候选的理由码（docs/modules/42 §5.3）。正向亮点 + 谨慎项。
 */
export type HighlightReason =
  | "HOOK_QUOTE"
  | "CLEAR_PAYOFF"
  | "HIGH_INFO_DENSITY"
  | "SURPRISE"
  | "EMOTIONAL_PEAK"
  | "SELF_CONTAINED"
  | "STRONG_TOPIC"
  | "VISUAL_ACTION"
  | "CONTEXT_DEPENDENT"
  | "TECHNICAL_DEFECT";
export type ReasonCodes = HighlightReason[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 加权 highlight_score，可为负（惩罚项占优时）
 */
export type Score = number;
/**
 * 构成窗口的转录段，句子边界
 */
export type SegmentIds = string[];
export type SourceTranscriptId = string | null;
export type StartMs = number;
export type WeightsVersion = string | null;
export type Candidates = HighlightCandidate[];
export type CreatedAt = string;
export type FeatureProvider = string | null;
export type Id1 = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type SourceTranscriptId1 = string | null;
export type WeightsVersion1 = string | null;

/**
 * 一次热门片段识别的 Top-N 结果集（docs/modules/42 §5.3）。
 */
export interface HighlightSet {
  candidates?: Candidates;
  created_at: CreatedAt;
  feature_provider?: FeatureProvider;
  id: Id1;
  schema_version?: SchemaVersion2;
  source_transcript_id?: SourceTranscriptId1;
  weights_version?: WeightsVersion1;
}
/**
 * 一个热门片段候选（docs/modules/42 §5）。时间窗落在句子边界，附特征/评分/理由/人工标签。
 */
export interface HighlightCandidate {
  end_ms: EndMs;
  features: HighlightFeatures;
  human_label?: HighlightLabel;
  human_label_reason?: HumanLabelReason;
  id: Id;
  predicted_retention?: PredictedRetention;
  reason_codes?: ReasonCodes;
  schema_version?: SchemaVersion1;
  score: Score;
  segment_ids?: SegmentIds;
  source_transcript_id?: SourceTranscriptId;
  start_ms: StartMs;
  weights_version?: WeightsVersion;
}
/**
 * 单个候选窗口的 11 项特征子分（docs/modules/42 §5.2），各 ∈ [0,1]。由模型判断产出。
 */
export interface HighlightFeatures {
  context_dependency: ContextDependency;
  emotional_energy: EmotionalEnergy;
  ending_payoff: EndingPayoff;
  hook_strength: HookStrength;
  information_density: InformationDensity;
  schema_version?: SchemaVersion;
  self_containedness: SelfContainedness;
  speaker_prominence: SpeakerProminence;
  surprise_or_conflict: SurpriseOrConflict;
  technical_defect: TechnicalDefect;
  topic_relevance: TopicRelevance;
  visual_activity: VisualActivity;
}
