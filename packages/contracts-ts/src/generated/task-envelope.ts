/* eslint-disable */
/**
 * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。
 * 再生成：pnpm --filter @videoforge/contracts generate
 */

export type Attempt = number;
/**
 * 能力标识，如 media.probe / asr.transcribe
 */
export type Capability = string;
export type CreatedAt = string;
/**
 * 短期凭据句柄（非凭据本体）
 */
export type CredentialHandles = string[];
/**
 * 任务路由策略（docs/architecture/30 §6）。
 */
export type ExecutionPolicy = "LOCAL_ONLY" | "LOCAL_PREFERRED" | "CLOUD_PREFERRED" | "CLOUD_ONLY";
/**
 * 重复提交按 task_id + output_digest 幂等
 */
export type IdempotencyKey = string;
export type InputArtifactIds = string[];
export type LeaseExpiresAt = string | null;
export type LeaseId = string | null;
/**
 * 产物需满足的 schema 引用，如 schemas/artifact.schema.json
 */
export type OutputSchemaRef = string | null;
export type Priority = number;
export type CpuCores = number | null;
export type Gpu = boolean | null;
export type MemoryMb = number | null;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion = string;
/**
 * 单次尝试的硬超时
 */
export type TimeoutS = number;
/**
 * 合同 schema 版本；Reader 需兼容当前与前一版本
 */
export type SchemaVersion1 = string;
export type TaskId = string;
export type WorkflowId = string | null;

/**
 * Worker 领取的任务信封（docs/architecture/30 §5 Task Lease 协议）。
 */
export interface TaskEnvelope {
  attempt: Attempt;
  capability: Capability;
  created_at: CreatedAt;
  credential_handles?: CredentialHandles;
  execution_policy?: ExecutionPolicy;
  idempotency_key: IdempotencyKey;
  input_artifact_ids?: InputArtifactIds;
  lease_expires_at?: LeaseExpiresAt;
  lease_id?: LeaseId;
  output_schema_ref?: OutputSchemaRef;
  params?: Params;
  priority?: Priority;
  resource_limits?: ResourceLimits | null;
  schema_version?: SchemaVersion1;
  task_id: TaskId;
  workflow_id?: WorkflowId;
}
/**
 * 能力专属参数；禁止任何明文凭据字段（用 credential_handles）
 */
export interface Params {
  [k: string]: unknown;
}
export interface ResourceLimits {
  cpu_cores?: CpuCores;
  gpu?: Gpu;
  memory_mb?: MemoryMb;
  schema_version?: SchemaVersion;
  timeout_s: TimeoutS;
}
