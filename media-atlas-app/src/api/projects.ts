/** M-W3 项目工作台 + M-W4 分析链（apps/api projects.py）。 */
import { api } from "./client";
import type { CreationMode } from "./trends";

export type ProjectStatus =
  | "DRAFT"
  | "INGESTING"
  | "ANALYZING"
  | "PLANNING"
  | "EDITING"
  | "LOCALIZING"
  | "QC"
  | "REVIEW"
  | "APPROVED"
  | "PUBLISHING"
  | "WAITING_FOR_HUMAN"
  | "PUBLISHED"
  | "MEASURING"
  | "COMPLETED"
  | "FAILED";

export interface Project {
  id: string;
  title: string;
  vertical: string;
  source_language: string;
  target_languages: string[];
  creation_mode: CreationMode;
  version: number;
  status: ProjectStatus;
  execution_policy: string;
  trend_cluster_id: string | null;
  source_asset_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface AnalysisStageView {
  stage: string;
  status: string;
  cache_key: string | null;
  cache_hit: boolean;
  artifact_id: string | null;
  provider: string | null;
  error: string | null;
  issues: string[];
}

export interface AnalysisRunView {
  id: string;
  project_id: string;
  source_asset_id: string;
  language: string;
  status: string;
  stages: AnalysisStageView[];
}

export function listProjects(limit = 50): Promise<Project[]> {
  return api.get<Project[]>("/v1/projects", { limit });
}

export function getProject(projectId: string): Promise<Project> {
  return api.get<Project>(`/v1/projects/${encodeURIComponent(projectId)}`);
}

/** 404 = 尚未做过分析（空态，不是错误）。 */
export function getLatestAnalysis(projectId: string): Promise<AnalysisRunView> {
  return api.get<AnalysisRunView>(`/v1/projects/${encodeURIComponent(projectId)}/analysis`);
}

/** 409 = 素材没有本地文件（诚实：先人工下载关联，不假装分析）——detail 原样展示。 */
export function runAnalysis(
  projectId: string,
  body: { source_asset_id: string; language: string },
): Promise<AnalysisRunView> {
  return api.post<AnalysisRunView>(`/v1/projects/${encodeURIComponent(projectId)}/analysis:run`, body);
}

export type AnalysisArtifactPath = "transcript" | "text-tracks" | "visual" | "blueprint";

/** 产物 payload 是合同对象的 JSON；只在用到的地方做局部结构断言。 */
export function getAnalysisArtifact(
  projectId: string,
  path: AnalysisArtifactPath,
): Promise<Record<string, unknown>> {
  return api.get<Record<string, unknown>>(
    `/v1/projects/${encodeURIComponent(projectId)}/analysis/${path}`,
  );
}
