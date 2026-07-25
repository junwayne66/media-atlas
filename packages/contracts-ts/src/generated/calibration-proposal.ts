/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type RankerKind = "TREND_HOT" | "HIGHLIGHT";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type TemplateVersion = string;
export type EnoughSamples = boolean;
export type RankCorrelation = number | null;
export type SampleCount = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type TemplateVersion1 = string;
export type TopK = number;
export type TopKHitRate = number | null;
/**
 * 校准决策。**故意没有"全量替换"值**——最强动作只是 EXPLORE（§11：先离线再少量探索）。
 */
export type CalibrationDecision = "KEEP_CURRENT" | "EXPLORE" | "INSUFFICIENT_SAMPLES";
export type ExplorationFraction = number;
export type GeneratedAt = string;
export type Improvement = number;
export type MaxExplorationFraction = number;
export type Note = string;
export type Promotable = boolean;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;

/**
 * 一次校准提案：当前 vs 候选权重 + 双方离线评估 + 决策。
 *
 * 交叉校验把 §11 红线变成合同硬拦：EXPLORE 必须 promotable 且 0<fraction≤max；非 EXPLORE 时
 * fraction 必须为 0；不可 promotable 却 EXPLORE；探索比例不得超上限。
 */
export interface CalibrationProposal {
  candidate: RankerWeights;
  candidate_eval: RankingEvalResult;
  current: RankerWeights;
  current_eval: RankingEvalResult;
  decision: CalibrationDecision;
  exploration_fraction: ExplorationFraction;
  generated_at: GeneratedAt;
  improvement: Improvement;
  max_exploration_fraction?: MaxExplorationFraction;
  note?: Note;
  promotable: Promotable;
  ranker_kind: RankerKind;
  schema_version?: SchemaVersion2;
}
/**
 * 排序器权重（通用线性表示；系数为 ≥0 幅度——正负号在打分公式里，承接 VF-101）。
 */
export interface RankerWeights {
  coefficients: Coefficients;
  ranker_kind: RankerKind;
  schema_version?: SchemaVersion;
  template_version: TemplateVersion;
}
export interface Coefficients {
  [k: string]: number;
}
/**
 * 一组权重在历史样本上的**离线**排序质量。样本不足或无方差时指标为 null。
 */
export interface RankingEvalResult {
  enough_samples: EnoughSamples;
  rank_correlation?: RankCorrelation;
  ranker_kind: RankerKind;
  sample_count: SampleCount;
  schema_version?: SchemaVersion1;
  template_version: TemplateVersion1;
  top_k: TopK;
  top_k_hit_rate?: TopKHitRate;
}
