/**
 * M-W1 热点池：/v1/trend-clusters 全族。
 *
 * 领域对象类型直接取自 `@videoforge/contracts`（由 schemas/*.schema.json 生成，
 * 与 contracts-py 的 TrendCluster 同源）——**纯 type-only 导入，运行时零依赖**。
 * 只有端点自有的请求/响应 DTO 才在本地声明。
 */
import type { CreationMode, Project, TrendCluster, TrendStage } from "@videoforge/contracts";

import { api } from "./client";

export type { CreationMode, TrendCluster, TrendStage };
export type { TrendSubScores } from "@videoforge/contracts";

export interface ListClustersQuery {
  stage?: TrendStage;
  vertical?: string;
  limit?: number;
}

export function listTrendClusters(q: ListClustersQuery = {}): Promise<TrendCluster[]> {
  return api.get<TrendCluster[]>("/v1/trend-clusters", {
    stage: q.stage,
    vertical: q.vertical,
    limit: q.limit ?? 50,
  });
}

export interface CreateProjectFromClusterRequest {
  title?: string | null;
  source_language: string;
  target_languages: string[];
  creation_mode: CreationMode;
}

/**
 * 一键建项目。注意：该端点**不收 expected_version**（trends.py `create_project_from_cluster`
 * 只按 cluster_id 读簇 + 建项目，不写簇本身，故无乐观锁参数）；仍可能 404（簇不存在）。
 */
export function createProjectFromCluster(
  clusterId: string,
  body: CreateProjectFromClusterRequest,
): Promise<Project> {
  return api.post<Project>(`/v1/trend-clusters/${encodeURIComponent(clusterId)}/projects`, body);
}

export interface RescoreRequest {
  expected_version: number;
}

export function rescoreCluster(clusterId: string, body: RescoreRequest): Promise<TrendCluster> {
  return api.post<TrendCluster>(`/v1/trend-clusters/${encodeURIComponent(clusterId)}/rescore`, body);
}
