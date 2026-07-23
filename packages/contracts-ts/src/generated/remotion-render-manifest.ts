/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type CreatedAt = string;
export type Id = string;
/**
 * 产出内容 sha256；未渲染前为 null
 */
export type OutputDigest = string | null;
/**
 * Remotion 组件类型（docs/modules/42 §8.3）。每个映射到 packages 中一个 React 组件路径。
 */
export type RemotionComposition = "CAPTIONS" | "INFO_CARD" | "DATA_CHART" | "BRAND_ANIMATION" | "LOWER_THIRD";
export type DurationMs = number;
/**
 * Remotion Root React 组件路径，须落在白名单内（domain 强制）
 */
export type EntryComponentPath = string;
/**
 * ≤120 fps 满足绝大多数场景
 */
export type Fps = number;
export type Height = number;
export type Id1 = string;
/**
 * 渲染输出路径，须落在白名单内
 */
export type OutputPath = string;
/**
 * 组件 Prop 键；限 JS 标识符规则
 */
export type Key = string;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Props = RemotionProp[];
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
/**
 * 源 CreativeTimeline id
 */
export type TimelineId = string;
/**
 * Remotion CLI/npm 版本，供复现
 */
export type ToolVersion = string;
export type Width = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion2 = string;
export type ToolVersion1 = string;

/**
 * 一次 Remotion 渲染的可复现清单（§8.3；对齐 VF-307 RenderManifest 语义）。
 */
export interface RemotionRenderManifest {
  created_at: CreatedAt;
  id: Id;
  input_digests?: InputDigests;
  output_digest?: OutputDigest;
  request: RemotionRenderRequest;
  schema_version?: SchemaVersion2;
  tool_version: ToolVersion1;
}
/**
 * {asset_id: sha256} 供缓存与重放
 */
export interface InputDigests {
  [k: string]: string;
}
/**
 * 一次 Remotion 渲染请求：组件 + Props + 时长 + 帧率 + 分辨率 + 组件入口路径。
 */
export interface RemotionRenderRequest {
  composition: RemotionComposition;
  duration_ms: DurationMs;
  entry_component_path: EntryComponentPath;
  fps: Fps;
  height: Height;
  id: Id1;
  output_path: OutputPath;
  props?: Props;
  schema_version?: SchemaVersion1;
  timeline_id: TimelineId;
  tool_version: ToolVersion;
  width: Width;
}
/**
 * 单个类型化 Prop——Remotion React 组件将以此消费。value 层层校验，禁 shell 元字符渗入。
 */
export interface RemotionProp {
  key: Key;
  schema_version?: SchemaVersion;
  value: Value;
}
/**
 * JSON 兼容值；str/int/float/bool/None/list/dict 递归校验
 */
export interface Value {
  [k: string]: unknown;
}
