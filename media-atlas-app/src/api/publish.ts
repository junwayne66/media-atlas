/** M-W8 发布：/v1/publish-jobs 全族 + 日历（apps/api publish.py）。执行器全部为 Fake，UI 必须明示。 */
import { api } from "./client";

export type PublishPlatform = "TIKTOK" | "DOUYIN";
export type PublishMethod =
  | "OFFICIAL_API"
  | "OFFICIAL_SHARE_SDK"
  | "BROWSER_AUTOMATION"
  | "ANDROID_DEVICE"
  | "MANUAL_EXPORT";
export type PublishState =
  | "PENDING"
  | "PREFLIGHT_BLOCKED"
  | "AWAITING_AUTH"
  | "UPLOADING"
  | "SUBMITTED"
  | "VERIFYING"
  | "SUCCEEDED"
  | "SUCCEEDED_RECONCILED"
  | "FAILED"
  | "WAITING_FOR_HUMAN";
export type ReviewSeverity = "INFO" | "WARNING" | "ERROR" | "FATAL";

export interface PublishAttempt {
  attempt: number;
  request_digest: string;
  external_upload_token: string | null;
  external_post_token: string | null;
  detail: string | null;
  at: string;
}

export interface PublishJob {
  id: string;
  idempotency_key: string;
  account_id: string;
  platform: PublishPlatform;
  method: PublishMethod;
  render_digest: string;
  metadata_digest: string;
  scheduled_window: string;
  state: PublishState;
  external_post_id: string | null;
  external_url: string | null;
  content_fingerprint: string | null;
  attempts: PublishAttempt[];
  created_at: string;
  updated_at: string;
}

export interface PreflightFinding {
  check: string;
  severity: ReviewSeverity;
  detail: string;
  evidence: Record<string, unknown>;
}

export interface PreflightReport {
  id: string;
  platform: PublishPlatform;
  method: PublishMethod;
  findings: PreflightFinding[];
  publishable: boolean;
  created_at: string;
}

export interface PublishJobView {
  job: PublishJob;
  row_version: number;
  render_manifest_id: string | null;
  /** 展示用历史报告；submit 被拦时后端会同步落库最新失败报告。 */
  preflight_report: PreflightReport | null;
  issues: string[];
}

export interface PublishMediaProbe {
  width: number;
  height: number;
  aspect_ratio: string;
  video_codec: string;
  audio_codec: string;
  container: string;
  file_size_bytes: number;
  duration_ms: number;
}

export interface PublishMetadata {
  title: string;
  description?: string;
  tags?: string[];
  language: string;
  cover_ref?: string | null;
}

export interface PublishJobCreate {
  account_id: string;
  platform: PublishPlatform;
  media_digest: string;
  metadata: PublishMetadata;
  render_manifest_id?: string | null;
  publishing_window?: string;
  copy_index?: number;
  method?: PublishMethod;
}

export interface PreflightResponse {
  report: PreflightReport;
  job: PublishJob;
}

export interface SubmitResponse {
  job: PublishJob;
  executor_status: string;
  idempotent_replay: boolean;
  detail: string | null;
}

export interface ReconcileResponse {
  job: PublishJob;
  found_post: boolean;
  attempts_count: number;
}

export interface NextPublishResponse {
  window: string;
  now: string;
  next_publish_time: string;
  immediate: boolean;
}

export interface ListJobsQuery {
  state?: PublishState;
  platform?: PublishPlatform;
  account_id?: string;
  limit?: number;
}

export function listPublishJobs(q: ListJobsQuery = {}): Promise<PublishJobView[]> {
  return api.get<PublishJobView[]>("/v1/publish-jobs", {
    state: q.state,
    platform: q.platform,
    account_id: q.account_id,
    limit: q.limit ?? 50,
  });
}

export function getPublishJob(jobId: string): Promise<PublishJobView> {
  return api.get<PublishJobView>(`/v1/publish-jobs/${encodeURIComponent(jobId)}`);
}

export function createPublishJob(body: PublishJobCreate): Promise<PublishJob> {
  return api.post<PublishJob>("/v1/publish-jobs", body);
}

/**
 * 预检。**请求体只传媒体探针**：元数据以建任务时入库的那份为准（它参与幂等键、建好后不可变），
 * 旧式带 `metadata` 的请求体会被 422 拒（docs/modules/45 §8）。
 */
export function runPreflight(jobId: string, probe: PublishMediaProbe): Promise<PreflightResponse> {
  return api.post<PreflightResponse>(`/v1/publish-jobs/${encodeURIComponent(jobId)}/preflight`, {
    probe,
  });
}

export function submitPublishJob(jobId: string): Promise<SubmitResponse> {
  return api.post<SubmitResponse>(`/v1/publish-jobs/${encodeURIComponent(jobId)}/submit`);
}

/** 对账——绝不盲目重发（§0.2 红线：这不是"重试"）。 */
export function reconcilePublishJob(jobId: string): Promise<ReconcileResponse> {
  return api.post<ReconcileResponse>(`/v1/publish-jobs/${encodeURIComponent(jobId)}/reconcile`);
}

export function manualCompletePublishJob(
  jobId: string,
  externalPostId: string,
  externalUrl?: string | null,
): Promise<PublishJob> {
  return api.post<PublishJob>(`/v1/publish-jobs/${encodeURIComponent(jobId)}/manual-complete`, {
    external_post_id: externalPostId,
    external_url: externalUrl ?? null,
  });
}

export function nextPublishTime(window: string): Promise<NextPublishResponse> {
  return api.get<NextPublishResponse>("/v1/publish-calendar/next", { window });
}

/** 状态机主干（WAITING_FOR_HUMAN 是分支，不在主干上）。 */
export const PUBLISH_MAIN_STATES: PublishState[] = [
  "PENDING",
  "UPLOADING",
  "SUBMITTED",
  "VERIFYING",
  "SUCCEEDED",
];

export const PUBLISH_STATE_LABEL: Record<PublishState, string> = {
  PENDING: "待处理",
  PREFLIGHT_BLOCKED: "预检阻断",
  AWAITING_AUTH: "等待授权",
  UPLOADING: "上传中",
  SUBMITTED: "已提交",
  VERIFYING: "核验中",
  SUCCEEDED: "已发布",
  SUCCEEDED_RECONCILED: "已发布(对账确认)",
  FAILED: "失败",
  WAITING_FOR_HUMAN: "等人工",
};

/**
 * 可提交态（与 publish.py `submit` 的起点一致）：PENDING / PREFLIGHT_BLOCKED / UPLOADING，
 * 且 attempts 里**没有** external_post_token（durable latch——已发过就绝不再发，VF-503 §5 幂等）。
 * 服务端仍会实时重跑预检 fail-closed；UI 这层只是不给出明显非法的入口。
 */
const SUBMITTABLE_STATES: PublishState[] = ["PENDING", "PREFLIGHT_BLOCKED", "UPLOADING"];

export function canSubmit(job: PublishJob): boolean {
  if (!SUBMITTABLE_STATES.includes(job.state)) return false;
  return !job.attempts.some((a) => a.external_post_token);
}
