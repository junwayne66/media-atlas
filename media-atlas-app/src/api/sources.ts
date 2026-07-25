/** M-W2 素材库：/v1/sources 族（形状以 apps/api sources.py 响应模型为准）。 */
import { api } from "./client";

export type SourceAssetKind = "URL" | "LOCAL_FILE";
export type SourceDisposition = "IMPORTED" | "MANUAL_FALLBACK" | "NEEDS_EXPANSION" | "UNRESOLVABLE";

export interface AcquisitionAttemptSummary {
  connector: string;
  status: string;
  error_code: string | null;
}

export interface AcquisitionSummary {
  tool_name: string;
  tool_version: string | null;
  output_sha256: string | null;
  attempts: AcquisitionAttemptSummary[];
  manual_fallback: boolean;
}

export interface SourceAsset {
  id: string;
  version: number;
  kind: SourceAssetKind;
  original_input: string;
  platform: string;
  content_id: string | null;
  canonical_url: string | null;
  disposition: SourceDisposition;
  reason: string;
  error_code: string | null;
  local_path: string | null;
  file_sha256: string | null;
  acquisition: AcquisitionSummary | null;
  project_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ResolveResponse {
  resolvable: boolean;
  platform: string;
  content_id: string | null;
  canonical_url: string | null;
  needs_expansion: boolean;
  short_url: string | null;
  reason: string;
  error_code: string | null;
}

export interface DuplicateGroupView {
  group_id: string;
  member_asset_ids: string[];
  layers: string[];
  similarity: number;
}

export interface ListSourcesQuery {
  platform?: string;
  disposition?: SourceDisposition;
  limit?: number;
}

export function listSources(q: ListSourcesQuery = {}): Promise<SourceAsset[]> {
  return api.get<SourceAsset[]>("/v1/sources", {
    platform: q.platform,
    disposition: q.disposition,
    limit: q.limit ?? 50,
  });
}

export function resolveSource(input: string): Promise<ResolveResponse> {
  return api.post<ResolveResponse>("/v1/sources:resolve", { input });
}

export function importUrl(input: string, projectId?: string | null): Promise<SourceAsset> {
  return api.post<SourceAsset>("/v1/sources/import-url", {
    input,
    project_id: projectId ?? null,
  });
}

export function importFile(path: string, projectId?: string | null): Promise<SourceAsset> {
  return api.post<SourceAsset>("/v1/sources/import-file", {
    path,
    project_id: projectId ?? null,
  });
}

export function listDuplicateGroups(): Promise<DuplicateGroupView[]> {
  return api.get<DuplicateGroupView[]>("/v1/sources/duplicate-groups");
}

/** disposition → 面向运营的中文文案；MANUAL_FALLBACK 是**流程**不是报错（§2 诚实展示）。 */
export const DISPOSITION_LABEL: Record<SourceDisposition, string> = {
  IMPORTED: "已导入",
  MANUAL_FALLBACK: "人工下载",
  NEEDS_EXPANSION: "待展开短链",
  UNRESOLVABLE: "无法解析",
};

export const DISPOSITION_HINT: Record<SourceDisposition, string> = {
  IMPORTED: "素材已入库，可用于分析。",
  MANUAL_FALLBACK: "live 下载未配置，请人工下载后关联本地文件（这是既定流程，不是错误）。",
  NEEDS_EXPANSION: "短链需先展开为规范链接；live 展开未接通，请粘贴展开后的链接。",
  UNRESOLVABLE: "链接无法解析为受支持的平台素材，请检查输入。",
};
