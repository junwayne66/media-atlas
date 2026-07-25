/**
 * M-W9 效果看板：/v1/performance 只读族（apps/api performance.py）。null 指标恒为 null，绝不当 0。
 *
 * `PerformanceSnapshot` / `PerformanceDashboard` / `AccountBaseline(Entry)` /
 * `PerformanceGroupStat` / `LearningReport` / `LearningSignalResult` / `SignalBucketStat`
 * 及枚举 `MetricField` / `GroupDimension` / `SignalDirection` 全部取自合同包（type-only，
 * 运行时零依赖）；`DashboardResponse` / `LearningResponse` / `CaptureResponse` 是
 * performance.py 自有的端点包装，保留本地声明。
 */
import type {
  AccountBaseline,
  GroupDimension,
  LearningReport,
  MetricField,
  PerformanceDashboard,
  PerformanceGroupStat,
  PerformanceSnapshot,
  PublishPlatform,
  SignalDirection,
} from "@videoforge/contracts";

import { api } from "./client";

export type {
  AccountBaseline,
  AccountBaselineEntry,
  GroupDimension,
  LearningReport,
  LearningSignalResult,
  MetricField,
  PerformanceDashboard,
  PerformanceGroupStat,
  PerformanceSnapshot,
  SignalBucketStat,
  SignalDirection,
  SignalKind,
} from "@videoforge/contracts";

export interface DashboardResponse {
  dashboard: PerformanceDashboard;
  baseline: AccountBaseline;
  ranked_groups: PerformanceGroupStat[];
  insufficient_groups: PerformanceGroupStat[];
  record_count: number;
  issues: string[];
}

export interface LearningResponse {
  report: LearningReport;
  record_count: number;
  issues: string[];
}

export interface CaptureResponse {
  snapshot: PerformanceSnapshot;
  created: boolean;
  issues: string[];
}

export interface PerformanceQuery {
  account_id: string;
  platform: PublishPlatform;
  age_hours?: number;
  metric?: MetricField;
  min_samples?: number;
}

export function getDashboard(q: PerformanceQuery): Promise<DashboardResponse> {
  return api.get<DashboardResponse>("/v1/performance/dashboard", {
    account_id: q.account_id,
    platform: q.platform,
    age_hours: q.age_hours ?? 24,
    metric: q.metric ?? "VIEWS",
    min_samples: q.min_samples ?? 5,
  });
}

export function getLearningReport(q: PerformanceQuery): Promise<LearningResponse> {
  return api.get<LearningResponse>("/v1/performance/learning-report", {
    account_id: q.account_id,
    platform: q.platform,
    age_hours: q.age_hours ?? 24,
    metric: q.metric ?? "VIEWS",
    min_samples: q.min_samples ?? 8,
  });
}

export function listSnapshots(postId: string): Promise<PerformanceSnapshot[]> {
  return api.get<PerformanceSnapshot[]>("/v1/performance/snapshots", { post_id: postId });
}

export function captureSnapshot(body: {
  account_id: string;
  platform: PublishPlatform;
  post_id: string;
  age_hours: number;
}): Promise<CaptureResponse> {
  return api.post<CaptureResponse>("/v1/performance/snapshots:capture", body);
}

/** demo 录制（apps/api/demo_recordings/metrics_demo.json）——用于默认查询值。 */
export const DEMO_ACCOUNT_ID = "demo-account";
export const DEMO_POST_IDS = ["demo-post-a", "demo-post-b"] as const;
export const DEMO_AGES_HOURS = [1, 24] as const;

export const METRIC_LABEL: Record<MetricField, string> = {
  VIEWS: "播放量",
  WATCH_TIME: "总观看时长",
  AVG_WATCH_TIME: "平均观看时长",
  COMPLETION_RATE: "完播率",
  LIKES: "点赞",
  COMMENTS: "评论",
  SHARES: "转发",
  SAVES: "收藏",
  FOLLOWS: "涨粉",
  IMPRESSIONS: "曝光",
  CLICK_THROUGH_RATE: "点击率",
};

export const DIMENSION_LABEL: Record<GroupDimension, string> = {
  TEMPLATE: "模板",
  HOOK: "Hook",
  CREATION_MODE: "创作模式",
  DURATION_BUCKET: "时长桶",
  LANGUAGE: "语言",
  PUBLISH_DAYPART: "发布时段",
};

export const DIRECTION_LABEL: Record<SignalDirection, string> = {
  POSITIVE: "正相关",
  NEGATIVE: "负相关",
  NONE: "无明显相关",
  INSUFFICIENT: "样本不足",
};

/** null ≠ 0：未采到就渲染 `—`（§0.2 红线 2）。 */
export function metricText(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return digits > 0 ? value.toFixed(digits) : value.toLocaleString("zh-CN");
}
