// 热点情报 API 客户端。经 vite 代理打到控制平面 /v1/trend-clusters。

export interface SubScores {
  velocity: number;
  acceleration: number;
  engagement_efficiency: number;
  cross_platform_score: number;
  topic_fit: number;
  novelty: number;
  source_quality: number;
  saturation: number;
  decay: number;
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
  stage: string;
  sub_scores: SubScores | null;
  hot_score: number | null;
  weights_version: string | null;
  reason_codes: string[];
  vertical: string | null;
  source_confidence: number;
}

export interface Project {
  id: string;
  title: string;
  trend_cluster_id: string | null;
  creation_mode: string;
}

const BASE = "/api/v1/trend-clusters";

async function unwrap<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${detail}`);
  }
  return (await resp.json()) as T;
}

export async function listClusters(
  params: { stage?: string; vertical?: string } = {},
): Promise<TrendCluster[]> {
  const q = new URLSearchParams();
  if (params.stage) q.set("stage", params.stage);
  if (params.vertical) q.set("vertical", params.vertical);
  return unwrap(await fetch(`${BASE}?${q.toString()}`));
}

export async function getCluster(id: string): Promise<TrendCluster> {
  return unwrap(await fetch(`${BASE}/${id}`));
}

function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => unwrap<T>(r));
}

export function rescoreCluster(id: string, expectedVersion: number): Promise<TrendCluster> {
  return post(`/${id}/rescore`, { expected_version: expectedVersion });
}

export function mergeCluster(
  id: string,
  body: { source_id: string; expected_version: number; reason: string },
): Promise<TrendCluster> {
  return post(`/${id}/merge`, body);
}

export function splitCluster(
  id: string,
  body: {
    member_item_ids: string[];
    expected_version: number;
    new_title: string;
    new_canonical_topic: string;
  },
): Promise<{ original: TrendCluster; created: TrendCluster }> {
  return post(`/${id}/split`, body);
}

export function createProjectFromCluster(
  id: string,
  body: { source_language: string; target_languages: string[]; creation_mode: string },
): Promise<Project> {
  return post(`/${id}/projects`, body);
}
