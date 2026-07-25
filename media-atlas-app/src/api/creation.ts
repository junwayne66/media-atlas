/** M-W5 创作：brief / claim-table / scripts / timeline / render-manifests（apps/api creation.py）。 */
import { api } from "./client";

/** 通用产物包装：payload 是对应合同对象的 JSON。 */
export interface DocumentView {
  id: string;
  project_id: string;
  kind: string;
  doc_version: number;
  cache_key: string | null;
  status: string | null;
  issues: string[];
  created_at: string | null;
  payload: Record<string, unknown>;
}

export interface ScriptSentence {
  id: string;
  beat_slot_id: string;
  role: string;
  text: string;
  target_duration_ms: number;
  claim_ids: string[];
  language: string;
  editable: boolean;
}

export interface ScriptVersion {
  id: string;
  version: number;
  language: string;
  sentences: ScriptSentence[];
  total_duration_ms: number | null;
  rewrite_provider: string | null;
  created_at: string;
}

export interface ScriptGenerateResponse {
  script: ScriptVersion;
  doc_version: number;
  status: string;
  issues: string[];
}

export interface CreativeBrief {
  id: string;
  objective: string;
  audience: string;
  platform: string;
  target_language: string;
  duration_target_ms: number;
  creation_mode: string;
  angle: string;
  hook: { type: string; promise: string } | null;
  must_cover_claim_ids: string[];
  avoid: string[];
  cta: string | null;
}

export function listScripts(projectId: string, limit = 50): Promise<DocumentView[]> {
  return api.get<DocumentView[]>(`/v1/projects/${encodeURIComponent(projectId)}/scripts`, { limit });
}

export function getBrief(projectId: string): Promise<DocumentView> {
  return api.get<DocumentView>(`/v1/projects/${encodeURIComponent(projectId)}/brief`);
}

/**
 * 生成脚本。409 有两种语义（creation.py `_error`）：
 * - 缺前置产物 → detail 说明缺什么（原样展示，不自动重试）；
 * - "产物版本冲突，请重试" → 并发撞版本号，调用方自动重试一次（§11 实现细节 ①）。
 */
export function generateScript(
  projectId: string,
  language?: string | null,
): Promise<ScriptGenerateResponse> {
  return api.post<ScriptGenerateResponse>(
    `/v1/projects/${encodeURIComponent(projectId)}/scripts:generate`,
    { language: language ?? null },
  );
}

/** 版本冲突文案（后端 creation.py 固定前缀）——只有它才允许自动重试一次。 */
export const DOC_VERSION_CONFLICT_MARK = "产物版本冲突";
