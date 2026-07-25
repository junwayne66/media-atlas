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
  SourceAssetKind,
  SourceDisposition,
} from "./generated/source-asset";

// —— M01 热点 ——
export type { TrendCluster, TrendStage, TrendSubScores } from "./generated/trend-cluster";

// —— M04 分析产物 ——
export type {
  Transcript,
  TranscriptModels,
  TranscriptSegment,
  TranscriptWord,
} from "./generated/transcript";
export type {
  BBox,
  TextObservation,
  TextTrack,
  TextTrackKind,
  TextTrackSet,
} from "./generated/text-track-set";
export type {
  FrameAnalysis,
  FrameSampleReason,
  VisualAnalysis,
} from "./generated/visual-analysis";
export type {
  Claim,
  ClaimSourceStatus,
  EvidenceSpan,
  RhetoricalBeat,
  RhetoricalBeatKind,
  VideoBlueprint,
  VisualBeat,
  VisualBeatKind,
} from "./generated/video-blueprint";

// —— M05 创作 ——
export type { BriefHook, CreativeBrief, VisualMix } from "./generated/creative-brief";
export type { ScriptSentence, ScriptVersion } from "./generated/script-version";

// —— M07 审核 ——
export type {
  ReviewDecision,
  ReviewDecisionKind,
  ReviewScope,
} from "./generated/review-decision";

// —— M08 发布 ——
export type {
  PublishAttempt,
  PublishJob,
  PublishMethod,
  PublishPlatform,
  PublishState,
} from "./generated/publish-job";
export type {
  PreflightCheck,
  PreflightFinding,
  PreflightReport,
  ReviewSeverity,
} from "./generated/preflight-report";

// —— M09 效果反馈 ——
export type { PerformanceSnapshot } from "./generated/performance-snapshot";
export type {
  AccountBaseline,
  AccountBaselineEntry,
  MetricField,
} from "./generated/account-baseline";
export type {
  GroupDimension,
  PerformanceDashboard,
  PerformanceGroupStat,
} from "./generated/performance-dashboard";
export type { LearningReport } from "./generated/learning-report";
export type {
  LearningSignalResult,
  SignalBucketStat,
  SignalDirection,
  SignalKind,
} from "./generated/learning-signal-result";
