/** M-W9 效果看板：/v1/performance 只读族（apps/api performance.py）。null 指标恒为 null，绝不当 0。 */
import { api } from "./client";
import type { PublishPlatform } from "./publish";

export type MetricField =
  | "VIEWS"
  | "WATCH_TIME"
  | "AVG_WATCH_TIME"
  | "COMPLETION_RATE"
  | "LIKES"
  | "COMMENTS"
  | "SHARES"
  | "SAVES"
  | "FOLLOWS"
  | "IMPRESSIONS"
  | "CLICK_THROUGH_RATE";

export type GroupDimension =
  | "TEMPLATE"
  | "HOOK"
  | "CREATION_MODE"
  | "DURATION_BUCKET"
  | "LANGUAGE"
  | "PUBLISH_DAYPART";

export type SignalDirection = "POSITIVE" | "NEGATIVE" | "NONE" | "INSUFFICIENT";

export interface PerformanceSnapshot {
  id: string;
  platform: PublishPlatform;
  platform_post_id: string;
  account_id: string;
  observed_at: string;
  age_hours: number;
  views: number | null;
  watch_time_ms: number | null;
  avg_watch_time_ms: number | null;
  completion_rate: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  saves: number | null;
  follows: number | null;
  impressions: number | null;
  click_through_rate: number | null;
  source_confidence: number;
}

export interface AccountBaselineEntry {
  age_hours: number;
  metric: MetricField;
  median: number | null;
  p25: number | null;
  p75: number | null;
  sample_count: number;
}

export interface PerformanceGroupStat {
  dimension: GroupDimension;
  value: string;
  age_hours: number;
  metric: MetricField;
  sample_count: number;
  median_relative: number | null;
  p25_relative: number | null;
  p75_relative: number | null;
  /** false → 进"样本不足"折叠区，不参与排序（§0.2 红线 6）。 */
  enough_samples: boolean;
}

export interface DashboardResponse {
  dashboard: {
    account_id: string;
    platform: PublishPlatform;
    age_hours: number;
    metric: MetricField;
    baseline: AccountBaselineEntry;
    min_samples: number;
    group_stats: PerformanceGroupStat[];
  };
  baseline: { account_id: string; platform: PublishPlatform; entries: AccountBaselineEntry[] };
  ranked_groups: PerformanceGroupStat[];
  insufficient_groups: PerformanceGroupStat[];
  record_count: number;
  issues: string[];
}

export interface SignalBucketStat {
  label: string;
  sample_count: number;
  median_relative: number | null;
  enough_samples: boolean;
}

export interface LearningSignalResult {
  signal: string;
  metric: MetricField;
  age_hours: number;
  correlation: number | null;
  direction: SignalDirection;
  sample_count: number;
  enough_samples: boolean;
  buckets: SignalBucketStat[];
  /** 后端恒 true——文案只能说"相关"，禁用"导致"（§0.2 红线 7）。 */
  association_only: boolean;
  note: string;
}

export interface LearningResponse {
  report: {
    account_id: string;
    platform: PublishPlatform;
    age_hours: number;
    metric: MetricField;
    min_samples: number;
    signals: LearningSignalResult[];
  };
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
