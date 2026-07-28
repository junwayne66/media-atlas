<template>
  <AppLayout>
    <div class="dashboard-view">
      <!-- Project Header -->
      <div class="project-header">
        <div class="project-info">
          <div class="title-row">
            <select v-model="selectedProjectId" class="project-select" :disabled="projects.loading.value">
              <option value="">选择项目…</option>
              <option v-for="p in projects.data.value ?? []" :key="p.id" :value="p.id">
                {{ p.title }}
              </option>
            </select>
            <h1 class="project-title">{{ current ? current.title : "未选择项目" }}</h1>
          </div>
          <div class="project-meta">
            <span v-if="current" class="meta-item">
              <StatusBadge :variant="statusVariant" :label="current.status ?? '—'" />
            </span>
            <span v-if="current" class="meta-item mono" :title="current.id">{{ shortId(current.id, 12) }}</span>
            <span v-if="current" class="meta-item">创建于 {{ datetime(current.created_at) }}</span>
            <span v-if="current" class="meta-item">{{ current.creation_mode }}</span>
            <span v-if="current" class="meta-item mono">
              {{ current.source_language }} → {{ current.target_languages.join(", ") || "—" }}
            </span>
          </div>
        </div>
        <div class="project-actions">
          <button class="btn btn-secondary" :disabled="!current" @click="reloadDetail">刷新</button>
        </div>
      </div>

      <StateBlock v-if="projects.error.value" kind="error" :title="projects.offline.value ? '无法连接控制面 API' : '项目列表拉取失败'" :detail="projects.error.value" />
      <StateBlock
        v-else-if="!projects.loading.value && (projects.data.value?.length ?? 0) === 0"
        kind="empty"
        title="还没有项目：已成功拉取，后端尚无 Project 记录。去「热点池」用「建项目」创建第一个。"
      />
      <StateBlock v-else-if="!current" kind="empty" title="请在上方下拉框选择一个项目查看流水线。" />

      <template v-else>
        <!-- Pipeline Card -->
        <div class="pipeline-card">
          <div class="pipeline-header">
            <h2 class="section-title">流水线阶段</h2>
            <div class="legend">
              <span class="legend-item"><span class="legend-dot legend-success"></span>完成</span>
              <span class="legend-item"><span class="legend-dot legend-info"></span>进行中</span>
              <span class="legend-item"><span class="legend-dot legend-neutral"></span>待开始 / 未接入</span>
            </div>
          </div>

          <div class="pipeline-stages">
            <div v-for="(stage, i) in pipelineStages" :key="stage.name" class="pipeline-stage-group">
              <div class="pipeline-stage">
                <div class="stage-icon" :class="`stage-${stage.status}`">
                  <img :src="stage.icon" alt="" />
                </div>
                <span class="stage-name">{{ stage.name }}</span>
                <StatusBadge :variant="stage.status" :label="stage.statusText" />
              </div>
              <div
                v-if="i < pipelineStages.length - 1"
                class="stage-connector"
                :class="{ 'connector-active': stage.status === 'success' }"
              ></div>
            </div>
          </div>
        </div>

        <!-- Bottom Row -->
        <div class="bottom-row">
          <!-- Todo Card -->
          <div class="todo-card">
            <div class="card-header-row">
              <h3 class="card-title">待办事项</h3>
              <span class="count-pill mono">{{ todos.length }}</span>
            </div>

            <StateBlock
              v-if="todos.length === 0"
              kind="empty"
              title="当前项目没有待人工处理项（分析阶段无错误、脚本无 issue）。"
            />
            <div v-for="(todo, i) in todos" :key="i" class="todo-item">
              <div class="todo-left">
                <StatusBadge :variant="todo.variant" :label="todo.statusText" />
                <span class="todo-text">{{ todo.text }}</span>
              </div>
              <span class="todo-meta mono">{{ todo.meta }}</span>
            </div>
          </div>

          <!-- Summary Card -->
          <div class="summary-card">
            <h3 class="card-title">项目摘要</h3>
            <div v-for="(row, i) in summaryRows" :key="i" class="summary-row">
              <span class="summary-label">{{ row.label }}</span>
              <span class="summary-value mono" :class="`value-${row.variant}`">{{ row.value }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import AppLayout from "@/components/AppLayout.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import StateBlock from "@/components/StateBlock.vue";
import { useAsync } from "@/composables/useAsync";
import { useSelectedProject } from "@/composables/useSelectedProject";
import { getLatestAnalysis, listProjects, type AnalysisRunView, type Project } from "@/api/projects";
import { listScripts, type DocumentView } from "@/api/creation";
import { datetime, shortId } from "@/utils/format";

type Variant = "success" | "warning" | "error" | "info" | "neutral";

const { selectedProjectId } = useSelectedProject();

const projects = useAsync<Project[]>();
const analysis = useAsync<AnalysisRunView>();
const scripts = useAsync<DocumentView[]>();

function icon(name: string) {
  return new URL(`../assets/svg/${name}.svg`, import.meta.url).href;
}

const current = computed<Project | null>(
  () => (projects.data.value ?? []).find((p) => p.id === selectedProjectId.value) ?? null,
);

const statusVariant = computed<Variant>(() => {
  const s = current.value?.status;
  if (!s) return "neutral";
  if (s === "FAILED") return "error";
  if (s === "WAITING_FOR_HUMAN") return "warning";
  if (s === "COMPLETED" || s === "PUBLISHED" || s === "APPROVED") return "success";
  if (s === "DRAFT") return "neutral";
  return "info";
});

/**
 * 阶段状态取自各域对象的存在性（§3）。后端尚无 project 关联的域（本地化 / QA / 发布 / 效果）
 * 一律标"未接入"而不是伪造"待开始"——诚实优先。
 */
const pipelineStages = computed(() => {
  const run = analysis.data.value;
  const scriptDocs = scripts.data.value ?? [];
  const hasSource = (current.value?.source_asset_ids?.length ?? 0) > 0;

  const analysisStatus: Variant = run
    ? run.stages.some((s) => s.error)
      ? "error"
      : run.status === "COMPLETED" || run.status === "SUCCEEDED"
        ? "success"
        : "info"
    : "neutral";
  const analysisText = run ? run.status : analysis.notFound.value ? "未分析" : "—";

  return [
    {
      name: "采集",
      status: (hasSource ? "success" : "neutral") as Variant,
      statusText: hasSource ? `${current.value?.source_asset_ids?.length} 条素材` : "无素材",
      icon: icon("2_97"),
    },
    { name: "分析", status: analysisStatus, statusText: analysisText, icon: icon("10_9") },
    {
      name: "创作",
      status: (scriptDocs.length > 0 ? "success" : "neutral") as Variant,
      statusText: scriptDocs.length > 0 ? `v${scriptDocs[0]?.doc_version ?? 1}` : "未生成",
      icon: icon("10_200"),
    },
    { name: "本地化", status: "neutral" as Variant, statusText: "未接入", icon: icon("10_278") },
    { name: "QA", status: "neutral" as Variant, statusText: "未接入", icon: icon("2_80") },
    { name: "审核", status: "neutral" as Variant, statusText: "见审核页", icon: icon("10_318") },
    { name: "发布", status: "neutral" as Variant, statusText: "见发布页", icon: icon("2_82") },
    { name: "效果", status: "neutral" as Variant, statusText: "见效果页", icon: icon("2_84") },
  ];
});

const todos = computed(() => {
  const items: { variant: Variant; statusText: string; text: string; meta: string }[] = [];
  for (const stage of analysis.data.value?.stages ?? []) {
    if (stage.error) {
      items.push({ variant: "error", statusText: "分析失败", text: `${stage.stage}: ${stage.error}`, meta: stage.provider ?? "—" });
    }
    for (const issue of stage.issues) {
      items.push({ variant: "warning", statusText: "需人工", text: `${stage.stage}: ${issue}`, meta: stage.provider ?? "—" });
    }
  }
  for (const doc of scripts.data.value ?? []) {
    if (doc.status && doc.status !== "OK") {
      items.push({
        variant: "warning",
        statusText: doc.status,
        text: `脚本 v${doc.doc_version}: ${doc.issues.join("; ") || "需复核"}`,
        meta: datetime(doc.created_at),
      });
    }
  }
  return items;
});

const summaryRows = computed<{ label: string; value: string; variant: string }[]>(() => {
  const p = current.value;
  if (!p) return [];
  const run = analysis.data.value;
  return [
    { label: "素材数量", value: String((p.source_asset_ids ?? []).length), variant: "primary" },
    { label: "脚本版本数", value: String((scripts.data.value ?? []).length), variant: "primary" },
    {
      label: "分析缓存命中",
      value: run ? `${run.stages.filter((s) => s.cache_hit).length} / ${run.stages.length}` : "—",
      variant: "primary",
    },
    { label: "来源热点簇", value: p.trend_cluster_id ? shortId(p.trend_cluster_id, 12) : "—", variant: "primary" },
    { label: "更新时间", value: datetime(p.updated_at), variant: "primary" },
  ];
});

async function reloadDetail(): Promise<void> {
  const id = selectedProjectId.value;
  if (!id) {
    analysis.reset();
    scripts.reset();
    return;
  }
  // 分析 404 = 尚未分析（空态，不是错误）；useAsync 已把 notFound 单列出来
  await Promise.all([analysis.run(() => getLatestAnalysis(id)), scripts.run(() => listScripts(id))]);
}

watch(selectedProjectId, () => void reloadDetail());

onMounted(async () => {
  const list = await projects.run(() => listProjects(50));
  if (!selectedProjectId.value && list && list.length > 0) {
    selectedProjectId.value = list[0]!.id;
  } else {
    await reloadDetail();
  }
});
</script>

<style scoped>
.dashboard-view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 100%;
}

/* ===== Project Header ===== */
.project-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.project-select {
  height: 32px;
  padding: 0 10px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
  font-family: inherit;
  cursor: pointer;
  max-width: 260px;
}

.project-title {
  font-size: var(--font-size-3xl);
  font-weight: 600;
  color: var(--color-text-primary);
}

.project-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: 500;
  transition: all 150ms ease;
  cursor: pointer;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-primary);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--color-bg-hover);
}

/* ===== Pipeline Card ===== */
.pipeline-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.pipeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.legend {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-success {
  background: var(--color-status-success);
}

.legend-info {
  background: var(--color-status-info);
}

.legend-neutral {
  background: var(--color-status-neutral);
}

.pipeline-stages {
  display: flex;
  align-items: center;
  gap: 0;
}

.pipeline-stage-group {
  display: flex;
  align-items: center;
  flex: 1;
}

.pipeline-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.stage-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  border: 2px solid var(--color-border-subtle);
}

.stage-icon img {
  width: 20px;
  height: 20px;
  opacity: 0.6;
}

.stage-success .stage-icon,
.stage-success {
  border-color: var(--color-status-success);
}

.stage-success .stage-icon img {
  opacity: 1;
  filter: brightness(1.2);
}

.stage-info .stage-icon {
  border-color: var(--color-status-info);
  background: rgba(0, 255, 255, 0.08);
}

.stage-info .stage-icon img {
  opacity: 1;
}

.stage-error .stage-icon {
  border-color: var(--color-status-error);
}

.stage-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.stage-connector {
  width: 24px;
  height: 2px;
  background: var(--color-border-strong);
  flex-shrink: 0;
}

.connector-active {
  background: var(--color-status-success);
}

/* ===== Bottom Row ===== */
.bottom-row {
  display: flex;
  gap: 16px;
}

.todo-card {
  flex: 1;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.count-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 18px;
  padding: 0 4px;
  background: var(--color-accent-primary);
  color: #fff;
  font-size: 10px;
  border-radius: var(--radius-sm);
}

.todo-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  padding: 12px 16px;
}

.todo-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.todo-text {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
}

.todo-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

/* ===== Summary Card ===== */
.summary-card {
  width: 380px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex-shrink: 0;
}

.summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.summary-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.summary-value {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.value-warning {
  color: var(--color-status-warning);
}

.summary-card .summary-row + .summary-row {
  padding-top: 12px;
  border-top: 1px solid var(--color-border-subtle);
}
</style>
