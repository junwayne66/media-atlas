// 手工维护的出口：只显式导出顶层合同与共享枚举的规范来源。
// 共享枚举（ExecutionPolicy 等）会在多个生成文件中重复出现，
// `export *` 会因歧义被 TS 静默丢弃，因此这里必须显式指定。
export type {
  Artifact,
  MediaProbe,
  ProducedBy,
  StorageBackend,
  StorageRef,
} from "./generated/artifact";
export type { ProblemDetail } from "./generated/problem-detail";
export type { CreationMode, ExecutionPolicy, Project, ProjectStatus } from "./generated/project";
export type {
  CostModel,
  HealthState,
  IsolationLevel,
  ProviderDescriptor,
  ProviderHealth,
  ProviderType,
} from "./generated/provider-descriptor";
export type { ResourceLimits, TaskEnvelope } from "./generated/task-envelope";
export type {
  AcquisitionAttemptSummary,
  AcquisitionSummary,
  SourceAsset,
} from "./generated/source-asset";
