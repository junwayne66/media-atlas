/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type Entities = string[];
/**
 * 至少一条证据，禁凭空 Claim
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
export type Id = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * Claim 的来源核验状态（docs/modules/41 §10.1）。
 */
export type ClaimSourceStatus = "VERIFIED" | "UNVERIFIED" | "DISPUTED" | "OPINION";
export type Text = string;
export type Claims = Claim[];
/**
 * rhetorical 节拍时间覆盖率（§10.2 目标 ≥0.9）
 */
export type Coverage = number | null;
export type CreatedAt = string;
export type DurationMs = number;
export type FusionProvider = string | null;
export type Id1 = string;
/**
 * 本节拍提出的 Claim id
 */
export type ClaimIds = string[];
export type EndMs1 = number;
export type Id2 = string;
/**
 * 表达层节拍（docs/modules/41 §10.1）。UNCLASSIFIED 允许存在以保覆盖率。
 */
export type RhetoricalBeatKind =
  "HOOK" | "QUESTION" | "EVIDENCE" | "CONTRAST" | "DEMO" | "CONCLUSION" | "CTA" | "UNCLASSIFIED";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type StartMs1 = number;
export type Summary = string | null;
export type RhetoricalBeats = RhetoricalBeat[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
export type SourceArtifactId = string | null;
export type EndMs2 = number;
/**
 * 代表帧时间
 */
export type FrameTimeMs = number | null;
export type Id3 = string;
/**
 * 视觉层节拍（docs/modules/41 §10.1）。
 */
export type VisualBeatKind = "PERSON" | "SCREEN_RECORD" | "PRODUCT" | "B_ROLL" | "CARD" | "UNKNOWN";
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion4 = string;
export type StartMs2 = number;
export type VisualBeats = VisualBeat[];

/**
 * 视频蓝图：事实层 + 表达层 + 视觉层（§10）。经 validate_blueprint 强校验后方可下游消费。
 */
export interface VideoBlueprint {
  claims?: Claims;
  coverage?: Coverage;
  created_at: CreatedAt;
  duration_ms: DurationMs;
  fusion_provider?: FusionProvider;
  id: Id1;
  rhetorical_beats?: RhetoricalBeats;
  schema_version?: SchemaVersion3;
  source_artifact_id?: SourceArtifactId;
  visual_beats?: VisualBeats;
}
/**
 * 可核验陈述（事实层）。必须至少引用一条证据 span（§10.2）。
 */
export interface Claim {
  entities?: Entities;
  evidence: Evidence;
  id: Id;
  schema_version?: SchemaVersion1;
  source_status?: ClaimSourceStatus;
  text: Text;
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
/**
 * 表达层节拍。时间范围由程序候选，kind 由融合分类。
 */
export interface RhetoricalBeat {
  claim_ids?: ClaimIds;
  end_ms: EndMs1;
  id: Id2;
  kind: RhetoricalBeatKind;
  schema_version?: SchemaVersion2;
  start_ms: StartMs1;
  summary?: Summary;
}
/**
 * 视觉层节拍（画面功能）。
 */
export interface VisualBeat {
  end_ms: EndMs2;
  frame_time_ms?: FrameTimeMs;
  id: Id3;
  kind: VisualBeatKind;
  schema_version?: SchemaVersion4;
  start_ms: StartMs2;
}
