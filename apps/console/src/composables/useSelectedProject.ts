/**
 * 当前选中的项目（工作台 / 分析查看器 / 创作编辑共用）。
 * router 里这些页面没有 :id 参数，用 `?project=` query + localStorage 记忆传递。
 */
import { ref, watch } from "vue";

const STORAGE_KEY = "media-atlas.selected-project";

function initial(): string {
  const fromQuery = new URLSearchParams(window.location.search).get("project");
  if (fromQuery) return fromQuery;
  return window.localStorage.getItem(STORAGE_KEY) ?? "";
}

const selectedProjectId = ref<string>(initial());

watch(selectedProjectId, (id) => {
  if (id) window.localStorage.setItem(STORAGE_KEY, id);
  else window.localStorage.removeItem(STORAGE_KEY);
});

export function useSelectedProject() {
  return { selectedProjectId };
}
