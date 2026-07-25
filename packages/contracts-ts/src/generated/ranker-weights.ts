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
