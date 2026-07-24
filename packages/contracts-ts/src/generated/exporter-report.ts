/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type BytesWritten = number | null;
export type Errors = string[];
/**
 * 时间线导出格式（docs/modules/42 §10）。DaVinci 优先 OTIO/FCPXML；剪映/CapCut 走 Adapter。
 */
export type ExporterKind = "OTIO_FILE" | "FCPXML" | "JIANYING" | "CAPCUT";
/**
 * 成功时为绝对路径；FAILED/UNSUPPORTED 时为 null
 */
export type OutputPath = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * 单个 Exporter 结果状态（docs/modules/42 §10：失败不阻断 MP4 最终渲染）。
 */
export type ExporterStatus = "OK" | "PARTIAL" | "FAILED" | "UNSUPPORTED";
/**
 * 导出器版本，供复现
 */
export type ToolVersion = string | null;
export type Warnings = string[];
export type Entries = ExportEntry[];
export type Id = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type TimelineId = string;

/**
 * 一次导出批次的报告：多 exporter 各自结果 + 时间戳。
 */
export interface ExporterReport {
  created_at: CreatedAt;
  entries?: Entries;
  id: Id;
  schema_version?: SchemaVersion1;
  timeline_id: TimelineId;
}
/**
 * 单个 Exporter 的输出结果（一份 timeline 可能同时导出到多种 NLE 格式）。
 */
export interface ExportEntry {
  bytes_written?: BytesWritten;
  errors?: Errors;
  kind: ExporterKind;
  output_path?: OutputPath;
  schema_version?: SchemaVersion;
  status: ExporterStatus;
  tool_version?: ToolVersion;
  warnings?: Warnings;
}
