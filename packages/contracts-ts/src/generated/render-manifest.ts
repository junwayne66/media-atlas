/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type DurationMs = number | null;
export type Id = string;
/**
 * 产出内容 sha256；未渲染前为 null
 */
export type OutputDigest = string | null;
/**
 * ffmpeg argv，绝无 shell 拼接
 *
 * @minItems 1
 */
export type Args = [string, ...string[]];
/**
 * ffmpeg 滤镜名，如 trim/setpts/scale/overlay
 */
export type Filter = string;
export type Id1 = string;
/**
 * 上游节点/输入流标签
 */
export type Inputs = string[];
/**
 * 本节点产出的标签
 *
 * @minItems 1
 */
export type Outputs = [string, ...string[]];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Nodes = FilterNode[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 终点标签，供 -map 引用
 */
export type Sinks = string[];
export type AssetId = string;
/**
 * 已解析的绝对路径
 */
export type ResolvedPath = string;
/**
 * video/audio/subtitle/…
 */
export type Role = string | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
/**
 * 内容哈希，可复现验证
 */
export type Sha256 = string;
export type Inputs1 = RenderInput[];
/**
 * 输出绝对路径
 */
export type OutputPath = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion3 = string;
/**
 * 渲染目标（编解码 + 封装）。
 */
export type RenderTargetKind = "MP4_H264" | "MP4_H265" | "MOV_PRORES" | "WEBM_VP9";
/**
 * ffmpeg 版本，供复现
 */
export type ToolVersion = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion4 = string;
/**
 * 渲染阶段（docs/modules/42 §8.3）。PROXY 供预览/审校，FINAL 供发布。
 */
export type RenderStage = "PROXY" | "FINAL";
/**
 * 源 CreativeTimeline id
 */
export type TimelineId = string;
export type ToolVersion1 = string;

/**
 * 一次渲染的可复现清单（§8.3）：输入哈希 + 工具版本 + 输出哈希 + 时间线来源。
 */
export interface RenderManifest {
  created_at: CreatedAt;
  duration_ms?: DurationMs;
  id: Id;
  input_digests?: InputDigests;
  output_digest?: OutputDigest;
  render_graph: FfmpegRenderGraph;
  schema_version?: SchemaVersion4;
  stage: RenderStage;
  timeline_id: TimelineId;
  tool_version: ToolVersion1;
}
/**
 * {asset_id: sha256} 供缓存与重放
 */
export interface InputDigests {
  [k: string]: string;
}
/**
 * FFmpeg 渲染指令：严格 argv 数组 + Filter Graph + 版本 pin。**绝不 shell 拼接**。
 */
export interface FfmpegRenderGraph {
  args: Args;
  filter_complex?: FilterGraph | null;
  inputs?: Inputs1;
  output_path: OutputPath;
  schema_version?: SchemaVersion3;
  target: RenderTargetKind;
  tool_version: ToolVersion;
}
/**
 * Filter Graph DAG：节点集合 + 边由 inputs/outputs 隐式定义。禁循环（domain 层拓扑校验）。
 */
export interface FilterGraph {
  nodes?: Nodes;
  schema_version?: SchemaVersion1;
  sinks?: Sinks;
}
/**
 * Filter Graph 单节点：滤镜名 + 参数字典 + 输入/输出标签。参数值受元字符拒绝。
 */
export interface FilterNode {
  filter: Filter;
  id: Id1;
  inputs?: Inputs;
  outputs: Outputs;
  params?: Params;
  schema_version?: SchemaVersion;
}
export interface Params {
  [k: string]: string;
}
/**
 * 一个渲染输入：素材身份 + 内容哈希 + 已解析的绝对路径（须在白名单内，由 domain 校验）。
 */
export interface RenderInput {
  asset_id: AssetId;
  resolved_path: ResolvedPath;
  role?: Role;
  schema_version?: SchemaVersion2;
  sha256: Sha256;
}
