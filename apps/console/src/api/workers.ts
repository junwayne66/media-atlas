/**
 * M-W10 Worker 队列（apps/api workers.py）。
 *
 * **能力边界（诚实登记）**：后端**没有** worker/worker-task 的 GET 列表端点——
 * 只有按 task_id 单查（`GET /v1/worker-tasks/{id}`）与人工 requeue。
 * 所以设置页只做"按 task_id 查询 + 终态 FAILED 人工恢复"，不伪造队列总览。
 */
import { api } from "./client";

export interface WorkerTaskStatus {
  task_id: string;
  status: string;
  attempt: number;
  max_attempts: number;
  capability: string;
  output: Record<string, unknown> | null;
  output_digest: string | null;
  leased_by: string | null;
  lease_expires_at: string | null;
}

export function getWorkerTask(taskId: string): Promise<WorkerTaskStatus> {
  return api.get<WorkerTaskStatus>(`/v1/worker-tasks/${encodeURIComponent(taskId)}`);
}

/** 终态 FAILED 的人工恢复（§0.2 红线 9：长任务终态可人工 requeue）。 */
export function requeueWorkerTask(taskId: string, maxAttempts?: number | null): Promise<void> {
  return api.post<void>(`/v1/worker-tasks/${encodeURIComponent(taskId)}/requeue`, {
    max_attempts: maxAttempts ?? null,
  });
}
