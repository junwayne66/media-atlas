/**
 * M-W2 素材库：/v1/sources 族。
 *
 * `SourceAsset` 及其 acquisition 摘要取自合同包；`ResolveResponse` /
 * `DuplicateGroupView` 是 sources.py 自有的端点形状（不是注册合同），保留本地声明。
 */
import type {
  AcquisitionAttemptSummary,
  AcquisitionSummary,
  SourceAsset,
  SourceAssetKind,
  SourceDisposition,
} from "@videoforge/contracts";

import { api } from "./client";

export type {
  AcquisitionAttemptSummary,
  AcquisitionSummary,
  SourceAsset,
  SourceAssetKind,
  SourceDisposition,
};

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
  METADATA_ONLY: "仅公开元数据",
};

export const DISPOSITION_HINT: Record<SourceDisposition, string> = {
  IMPORTED: "素材已入库，可用于分析。",
  MANUAL_FALLBACK: "live 下载未配置，请人工下载后关联本地文件（这是既定流程，不是错误）。",
  NEEDS_EXPANSION: "短链需先展开为规范链接；live 展开未接通，请粘贴展开后的链接。",
  UNRESOLVABLE: "链接无法解析为受支持的平台素材，请检查输入。",
  METADATA_ONLY: "已保存公开元数据；原始媒体尚未获得授权或尚未采集。",
};
