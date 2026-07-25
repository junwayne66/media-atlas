<template>
  <AppLayout>
    <div class="hotspots-view">
      <!-- Filter Bar -->
      <div class="filter-bar">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="filter-tab"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
        <div class="spacer"></div>
        <button class="filter-sort" @click="reload">
          <span>{{ state.loading.value ? "加载中…" : "热度排序 · 刷新" }}</span>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </div>

      <div v-if="notice" class="notice" :class="`notice--${notice.kind}`">
        <span class="notice-text">{{ notice.text }}</span>
        <button class="notice-close" @click="notice = null">×</button>
      </div>

      <!-- Trend Table -->
      <div class="trend-table">
        <StateBlock
          v-if="state.loading.value && !state.loaded.value"
          kind="loading"
          title="正在拉取热点簇…"
        />
        <StateBlock
          v-else-if="state.error.value"
          kind="error"
          :title="state.offline.value ? '无法连接控制面 API，热点池无法加载' : '热点簇拉取失败'"
          :detail="state.error.value"
        />
        <StateBlock
          v-else-if="rows.length === 0"
          kind="empty"
          :title="
            (state.data.value?.length ?? 0) === 0
              ? '热点池为空：已成功拉取，后端尚无热点簇记录。'
              : '当前分类下没有热点簇（已拉到 ' + (state.data.value?.length ?? 0) + ' 条，被筛选条件过滤）。'
          "
        />
        <DataTable v-else :columns="columns" :rows="rows" hoverable>
          <template #cell-title="{ row }">
            <div class="cell-title">
              <span class="hot-rank mono" :class="{ 'rank-top': row.rank <= 3 }">{{ row.rank }}</span>
              <div class="hot-title-wrap">
                <span class="hot-title">{{ row.title }}</span>
                <span v-if="row.reasons" class="hot-reasons">{{ row.reasons }}</span>
              </div>
            </div>
          </template>
          <template #cell-category="{ value }">
            <span class="category-tag">{{ value }}</span>
          </template>
          <template #cell-members="{ value }">
            <span class="mono">{{ value }}</span>
          </template>
          <template #cell-trend="{ row }">
            <span class="mono dim" :title="row.trendHint">—</span>
          </template>
          <template #cell-heatScore="{ value }">
            <span class="heat-score mono">{{ value }}</span>
          </template>
          <template #cell-status="{ value }">
            <StatusBadge :variant="value.variant" :label="value.label" />
          </template>
          <template #cell-actions="{ row }">
            <button class="action-btn" :disabled="creatingId === row.id" @click="createProject(row.id)">
              {{ creatingId === row.id ? "创建中…" : "建项目" }}
            </button>
          </template>
        </DataTable>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import AppLayout from "@/components/AppLayout.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import DataTable from "@/components/DataTable.vue";
import StateBlock from "@/components/StateBlock.vue";
import { useAsync } from "@/composables/useAsync";
import { useSelectedProject } from "@/composables/useSelectedProject";
import { ApiError, errorText, formatDetail } from "@/api/client";
import { createProjectFromCluster, listTrendClusters, type TrendCluster, type TrendStage } from "@/api/trends";

const router = useRouter();
const { selectedProjectId } = useSelectedProject();

const state = useAsync<TrendCluster[]>();
const activeTab = ref("all");
const creatingId = ref<string | null>(null);
const notice = ref<{ kind: "ok" | "warn" | "error"; text: string } | null>(null);

const STAGE_BADGE: Record<TrendStage, { variant: "success" | "warning" | "error" | "info" | "neutral"; label: string }> = {
  EMERGING: { variant: "info", label: "萌芽" },
  RISING: { variant: "success", label: "上升" },
  PEAK: { variant: "success", label: "峰值" },
  SATURATED: { variant: "warning", label: "饱和" },
  DECAYING: { variant: "warning", label: "衰退" },
  ARCHIVED: { variant: "neutral", label: "已归档" },
};

const columns = [
  { key: "title", label: "热点标题", flex: "2" },
  { key: "category", label: "分类", width: "90px" },
  { key: "members", label: "成员", width: "70px", align: "right" as const },
  { key: "trend", label: "7日趋势", width: "90px" },
  { key: "heatScore", label: "热度值", width: "90px", align: "right" as const },
  { key: "status", label: "阶段", width: "110px" },
  { key: "actions", label: "", width: "90px", align: "right" as const },
];

// vertical → 过滤 tab（真实值来自数据，不写死行业分类）
const tabs = computed(() => {
  const verticals = new Set<string>();
  for (const c of state.data.value ?? []) {
    if (c.vertical) verticals.add(c.vertical);
  }
  return [
    { key: "all", label: "全部" },
    ...[...verticals].sort().map((v) => ({ key: v, label: v })),
  ];
});

const rows = computed(() => {
  const clusters = state.data.value ?? [];
  const filtered = activeTab.value === "all" ? clusters : clusters.filter((c) => c.vertical === activeTab.value);
  return filtered.map((c, i) => ({
    id: c.id,
    rank: i + 1,
    title: c.title,
    // reason_codes 是热度判定证据，直接展示（可解释性）
    reasons: (c.reason_codes ?? []).join(" · "),
    category: c.vertical ?? "—",
    members: (c.member_item_ids ?? []).length,
    // 遗留：后端暂无 snapshot 序列查询端点，sparkline 无真实数据来源 → 渲染 `—`，绝不画假柱子
    trendHint: `后端暂无 snapshot 序列端点，趋势小图待接入（已关联 ${(c.snapshot_ids ?? []).length} 条快照）`,
    // null ≠ 0：热度未算出就是 `—`
    heatScore: c.hot_score == null ? "—" : String(Math.round(c.hot_score * 100)),
    status: (c.stage ? STAGE_BADGE[c.stage] : undefined) ?? {
      variant: "neutral" as const,
      label: c.stage ?? "—",
    },
  }));
});

async function reload(): Promise<void> {
  await state.run(() => listTrendClusters({ limit: 50 }));
}

async function createProject(clusterId: string): Promise<void> {
  creatingId.value = clusterId;
  notice.value = null;
  try {
    const project = await createProjectFromCluster(clusterId, {
      title: null,
      source_language: "zh-CN",
      target_languages: ["en-US"],
      creation_mode: "STRUCTURE_REWRITE",
    });
    selectedProjectId.value = project.id;
    await router.push({ path: "/dashboard", query: { project: project.id } });
  } catch (err) {
    if (err instanceof ApiError && err.isConflict) {
      // §0.2 红线 3：冲突不静默，展示原因并重新加载
      notice.value = { kind: "warn", text: `数据已被他人修改（409）：${formatDetail(err.detail) ?? ""} — 已重新加载列表` };
      await reload();
    } else {
      notice.value = { kind: "error", text: `建项目失败：${errorText(err)}` };
    }
  } finally {
    creatingId.value = null;
  }
}

onMounted(reload);
</script>

<style scoped>
.hotspots-view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
}

/* ===== Filter Bar ===== */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-tab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  padding: 0 12px;
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms ease;
}

.filter-tab:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.filter-tab.active {
  background: var(--color-bg-elevated);
  border-color: var(--color-accent-primary);
  color: var(--color-text-primary);
}

.spacer {
  flex: 1;
}

.filter-sort {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms ease;
}

.filter-sort:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

/* ===== Notice ===== */
.notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-primary);
}

.notice--warn {
  border-color: rgba(245, 166, 35, 0.4);
  color: var(--color-status-warning);
}

.notice--error {
  border-color: rgba(239, 68, 68, 0.4);
  color: var(--color-status-error);
}

.notice-close {
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: var(--font-size-xl);
  line-height: 1;
}

/* ===== Trend Table ===== */
.trend-table {
  flex: 1;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.cell-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.hot-rank {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-text-tertiary);
  min-width: 24px;
  text-align: center;
}

.rank-top {
  color: var(--color-status-warning);
}

.hot-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.hot-title {
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
  overflow: hidden;
  text-overflow: ellipsis;
}

.hot-reasons {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
}

.category-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 22px;
  padding: 0 8px;
  background: var(--color-bg-hover);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.mono.dim {
  color: var(--color-text-tertiary);
}

.heat-score {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 28px;
  padding: 0 12px;
  font-size: var(--font-size-xs);
  font-weight: 500;
  color: var(--color-accent-primary);
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 150ms ease;
}

.action-btn:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.2);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
