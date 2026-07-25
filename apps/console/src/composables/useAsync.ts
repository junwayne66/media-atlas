/**
 * 三态加载封装（docs/modules/45 §0.2 红线 1：空态 ≠ 错误态 ≠ 未配置态）。
 *
 * - `loading`：请求进行中
 * - `error`：拉取失败（含 `offline` = 压根没连上后端）
 * - `data` 为空数组/空对象：**拉过了确实没有** → 由视图渲染空态文案
 *
 * 绝不把失败静默成空列表。
 */
import { ref, shallowRef, type Ref, type ShallowRef } from "vue";
import { ApiError, errorText } from "@/api/client";

export interface AsyncState<T> {
  data: ShallowRef<T | null>;
  loading: Ref<boolean>;
  error: Ref<string | null>;
  /** true = 网络层没连上后端（未配置/服务未起），文案与业务错误区分。 */
  offline: Ref<boolean>;
  /** 后端明确返回 404（"还没有"）——视图可当空态而非错误。 */
  notFound: Ref<boolean>;
  loaded: Ref<boolean>;
  run: (fn: () => Promise<T>) => Promise<T | null>;
  reset: () => void;
}

export function useAsync<T>(initial: T | null = null): AsyncState<T> {
  const data = shallowRef<T | null>(initial);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const offline = ref(false);
  const notFound = ref(false);
  const loaded = ref(false);

  async function run(fn: () => Promise<T>): Promise<T | null> {
    loading.value = true;
    error.value = null;
    offline.value = false;
    notFound.value = false;
    try {
      const result = await fn();
      data.value = result;
      loaded.value = true;
      return result;
    } catch (err) {
      data.value = null;
      loaded.value = true;
      if (err instanceof ApiError) {
        offline.value = err.isOffline;
        notFound.value = err.isNotFound;
      }
      error.value = errorText(err);
      return null;
    } finally {
      loading.value = false;
    }
  }

  function reset(): void {
    data.value = initial;
    loading.value = false;
    error.value = null;
    offline.value = false;
    notFound.value = false;
    loaded.value = false;
  }

  return { data, loading, error, offline, notFound, loaded, run, reset };
}
