/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 产生词级时间的 provider 名（ASR / TTS forced align）
 */
export type AlignmentProvider = string | null;
export type CreatedAt = string;
export type EndMs = number;
export type Id = string;
/**
 * @minItems 1
 */
export type Lines = [SubtitleLine, ...SubtitleLine[]];
export type EndMs1 = number;
export type Language = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type StartMs = number;
export type Text = string;
export type Confidence = number | null;
export type EndMs2 = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type StartMs1 = number;
export type Text1 = string;
export type Words = SubtitleWord[];
export type BottomMaxPct = number;
export type LeftMinPct = number;
export type RightMaxPct = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type TopMinPct = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
export type SourceRefId = string | null;
/**
 * 源引用类型：transcript_segment / localized_sentence
 */
export type SourceRefKind = string | null;
export type StartMs2 = number;
/**
 * 引用 template.style_hint 或自定义
 */
export type StyleRef = string | null;
export type Cues = SubtitleCue[];
export type Id1 = string;
export type Language1 = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion4 = string;
export type SourceLocalizationVariantId = string | null;
export type SourceTranscriptId = string | null;
export type TemplateId = string;

/**
 * 一整轨字幕（同语言 + 同模板）。cues 应按 start_ms 严格排序、不重叠——由 domain 校验。
 */
export interface SubtitleTrack {
  alignment_provider?: AlignmentProvider;
  created_at: CreatedAt;
  cues?: Cues;
  id: Id1;
  language: Language1;
  schema_version?: SchemaVersion4;
  source_localization_variant_id?: SourceLocalizationVariantId;
  source_transcript_id?: SourceTranscriptId;
  template_id: TemplateId;
}
/**
 * 一条 cue（同屏同时显示的整块字幕）。lines 数量应 ≤ template.max_lines_per_cue。
 */
export interface SubtitleCue {
  end_ms: EndMs;
  id: Id;
  lines: Lines;
  /**
   * 按帧 occupied_regions 求解的安全区（若渲染层已算好可填）
   */
  safe_area_hint?: SafeAreaSpec | null;
  schema_version?: SchemaVersion3;
  source_ref_id?: SourceRefId;
  source_ref_kind?: SourceRefKind;
  start_ms: StartMs2;
  style_ref?: StyleRef;
}
/**
 * 一行字幕（cue 内多行的一条）。text 长度不宜超模板 max_chars_per_line（domain 校验）。
 */
export interface SubtitleLine {
  end_ms: EndMs1;
  language: Language;
  schema_version?: SchemaVersion;
  start_ms: StartMs;
  text: Text;
  words?: Words;
}
/**
 * 一行内的词级时间（karaoke / 逐词高亮）。仅在词级置信度达标时启用（§5.2）。
 */
export interface SubtitleWord {
  confidence?: Confidence;
  end_ms: EndMs2;
  schema_version?: SchemaVersion1;
  start_ms: StartMs1;
  text: Text1;
}
/**
 * 安全区约束（归一化百分比 0-100）；渲染/QA 消费。默认覆盖抖音/TikTok 底部 UI 占位。
 */
export interface SafeAreaSpec {
  bottom_max_pct?: BottomMaxPct;
  left_min_pct?: LeftMinPct;
  right_max_pct?: RightMaxPct;
  schema_version?: SchemaVersion2;
  top_min_pct?: TopMinPct;
}
