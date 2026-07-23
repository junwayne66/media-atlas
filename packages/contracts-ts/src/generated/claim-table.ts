/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
/**
 * 允许的表述方式
 */
export type AllowedPhrasings = string[];
export type ClaimId = string;
export type Confidence = number | null;
/**
 * 至少一条证据，禁凭空事实
 *
 * @minItems 1
 */
export type Evidence = [EvidenceSpan, ...EvidenceSpan[]];
export type EndMs = number;
/**
 * 证据来源类型
 */
export type Kind = string;
/**
 * 被引 transcript 段 id 或 TextTrack id
 */
export type RefId = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type StartMs = number;
/**
 * Claim 的来源核验状态（docs/modules/41 §10.1）。
 */
export type ClaimSourceStatus = "VERIFIED" | "UNVERIFIED" | "DISPUTED" | "OPINION";
/**
 * 时效标记，如 as_of_2026-07
 */
export type Recency = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type Text = string;
/**
 * 是否可直接用于改写（DISPUTED 须人工核实）
 */
export type UsableInRewrite = boolean;
export type Entries = ClaimTableEntry[];
export type Id = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type SourceBlueprintId = string | null;

/**
 * 经核验事实表，供结构重写消费。
 */
export interface ClaimTable {
  created_at: CreatedAt;
  entries?: Entries;
  id: Id;
  schema_version?: SchemaVersion2;
  source_blueprint_id?: SourceBlueprintId;
}
/**
 * ClaimTable 条目（docs/modules/42 §3.2）：事实 + 证据 + 时效 + 置信 + 允许表述。
 */
export interface ClaimTableEntry {
  allowed_phrasings?: AllowedPhrasings;
  claim_id: ClaimId;
  confidence?: Confidence;
  evidence: Evidence;
  fact_status?: ClaimSourceStatus;
  recency?: Recency;
  schema_version?: SchemaVersion1;
  text: Text;
  usable_in_rewrite?: UsableInRewrite;
}
/**
 * Claim 的证据来源：引用 transcript 段或 OCR 文本轨的时间片。
 */
export interface EvidenceSpan {
  end_ms: EndMs;
  kind: Kind;
  ref_id: RefId;
  schema_version?: SchemaVersion;
  start_ms: StartMs;
}
