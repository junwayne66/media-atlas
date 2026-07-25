/**
 * 控制面 REST 客户端（fetch 薄封装）。
 *
 * - base 默认 `/api`：开发期由 vite proxy 去前缀转发到 :8000，容器内由 nginx 同源反代。
 * - 错误统一成 `ApiError`：带 HTTP status + 结构化 detail（409/422 的 detail 原样透出，
 *   不做吞掉/改写——docs/modules/45 §0.2 红线 3「乐观锁冲突不静默」）。
 * - 网络失败/超时与业务错误分开：`status === 0` 表示压根没连上（未配置/服务未起），
 *   调用方据此区分"空态 / 错误态 / 未配置态"。
 */

const BASE: string = import.meta.env.VITE_API_BASE ?? "/api";
const DEFAULT_TIMEOUT_MS = 20_000;

/** FastAPI 422 的 detail 元素形状（只声明用到的字段）。 */
export interface ValidationDetailItem {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

/** 结构化 detail：后端有时给字符串，有时给 {message, issues} / {message, blocking_findings} / 422 数组。 */
export type ApiErrorDetail =
  | string
  | ValidationDetailItem[]
  | { message?: string; issues?: string[]; blocking_findings?: unknown; [k: string]: unknown }
  | null;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: ApiErrorDetail;
  readonly url: string;

  constructor(status: number, detail: ApiErrorDetail, url: string, message?: string) {
    super(message ?? formatDetail(detail) ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.url = url;
  }

  /** 网络层失败（未连上后端）——区别于后端返回的业务错误。 */
  get isOffline(): boolean {
    return this.status === 0;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }
}

/** 把任意 detail 拍平成可展示文案；结构化信息由调用方自行展开。 */
export function formatDetail(detail: ApiErrorDetail): string | null {
  if (detail == null) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const loc = (d.loc ?? []).join(".");
        return loc ? `${loc}: ${d.msg ?? ""}` : (d.msg ?? "");
      })
      .filter(Boolean)
      .join("; ");
  }
  const msg = typeof detail.message === "string" ? detail.message : null;
  const issues = Array.isArray(detail.issues) ? detail.issues.join("; ") : null;
  return [msg, issues].filter(Boolean).join(" — ") || JSON.stringify(detail);
}

/** 从任意抛出物提取可展示文案（模板里用）。 */
export function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.isOffline) return `无法连接后端 API：${err.message}`;
    return `HTTP ${err.status} · ${err.message}`;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}

export type QueryValue = string | number | boolean | null | undefined;

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = `${BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === null || v === undefined || v === "") continue;
    params.append(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

interface RequestOptions {
  query?: Record<string, QueryValue>;
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
}

async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, opts.query);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  if (opts.signal) {
    opts.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers: opts.body === undefined ? {} : { "Content-Type": "application/json" },
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: controller.signal,
    });
  } catch (err) {
    const reason = controller.signal.aborted ? `请求超时（${opts.timeoutMs ?? DEFAULT_TIMEOUT_MS}ms）` : String(err);
    throw new ApiError(0, reason, url, reason);
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 204) return undefined as T;

  const raw = await res.text();
  let parsed: unknown = null;
  if (raw) {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = raw;
    }
  }

  if (!res.ok) {
    const detail: ApiErrorDetail =
      parsed && typeof parsed === "object" && "detail" in (parsed as Record<string, unknown>)
        ? ((parsed as { detail: ApiErrorDetail }).detail)
        : ((parsed as ApiErrorDetail) ?? res.statusText);
    throw new ApiError(res.status, detail, url);
  }

  return parsed as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown, query?: Record<string, QueryValue>) =>
    request<T>("POST", path, { body: body ?? {}, query }),
};

export const API_BASE = BASE;
