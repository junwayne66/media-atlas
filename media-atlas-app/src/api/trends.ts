/** M-W1 热点池：/v1/trend-clusters 全族（字段以 apps/api trends.py 响应模型为准）。 */
import { api } from "./client";
import type { Project } from "./projects";

export type TrendStage = "EMERGING" | "RISING" | "PEAK" | "SATURATED" | "DECAYING" | "ARCHIVED";
export type CreationMode = "STRUCTURE_REWRITE" | "SOURCE_REEDIT";

export interface TrendSubScores {
  velocity: number;
  acceleration: number;
  engagement_efficiency: number;
  cross_platform_score?: number;
  topic_fit?: number;
  novelty?: number;
  source_quality?: number;
  saturation?: number;
  decay?: number;
}

export interface TrendCluster {
  id: string;
  version: number;
  title: string;
  canonical_topic: string;
  keywords: string[];
  entities: string[];
  member_item_ids: string[];
  snapshot_ids: string[];
  first_seen_at: string;
  last_seen_at: string;
  stage: TrendStage;
  sub_scores: TrendSubScores | null;
  /** null = 未算出热度，UI 渲染 `—`，绝不当 0（§0.2 红线 2）。 */
  hot_score: number | null;
  weights_version: string | null;
  reason_codes: string[];
  source_confidence: number;
  vertical: string | null;
  created_at: string;
  updated_at: string;
}

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
