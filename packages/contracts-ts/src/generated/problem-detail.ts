/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

/**
 * 机器可读错误码，如 PROVIDER_TIMEOUT（51 §2/§12）
 */
export type Code = string | null;
/**
 * 结构化上下文，如 {provider, attempt}
 */
export type Context = {
  [k: string]: unknown;
} | null;
/**
 * 跨服务关联 id，如 cor_...
 */
export type CorrelationId = string | null;
export type Detail = string | null;
/**
 * 本次出错请求的 URI/引用
 */
export type Instance = string | null;
/**
 * 调用方是否值得原样重试
 */
export type Retryable = boolean | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
export type Status = number;
export type Title = string;
/**
 * 问题类型 URI
 */
export type Type = string;

/**
 * RFC 9457 Problem Details；API 错误统一格式（docs/implementation/51 §2）。允许扩展字段。
 *
 * 禁止把栈、Cookie、Token、完整外部响应放进任何字段返回给客户端。
 */
export interface ProblemDetail {
  code?: Code;
  context?: Context;
  correlation_id?: CorrelationId;
  detail?: Detail;
  instance?: Instance;
  retryable?: Retryable;
  schema_version?: SchemaVersion;
  status: Status;
  title: Title;
  type?: Type;
  [k: string]: unknown;
}
