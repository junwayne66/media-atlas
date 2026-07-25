/**
 * M-W3 项目工作台 + M-W4 分析链（apps/api projects.py）。
 *
 * `Project` 取自合同包；`AnalysisRunView` / `AnalysisStageView` 是 projects.py 自有的
 * 编排视图（不是注册合同），保留本地声明。
 */
import type { Project, ProjectStatus } from "@videoforge/contracts";

import { api } from "./client";

export type { Project, ProjectStatus };

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
