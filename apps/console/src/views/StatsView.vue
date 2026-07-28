<template>
  <AppLayout>
    <div class="stats-view">
      <!-- Query bar -->
      <div class="query-bar">
        <label class="q-item">
          <span class="q-label">账号</span>
          <input v-model="q.account_id" class="q-input mono" type="text" />
        </label>
        <label class="q-item">
          <span class="q-label">平台</span>
          <select v-model="q.platform" class="q-input">
            <option value="TIKTOK">TIKTOK</option>
            <option value="DOUYIN">DOUYIN</option>
          </select>
        </label>
        <label class="q-item">
          <span class="q-label">时龄(h)</span>
          <input v-model.number="q.age_hours" class="q-input mono" type="number" min="0" step="1" />
        </label>
        <label class="q-item">
          <span class="q-label">指标</span>
          <select v-model="q.metric" class="q-input">
            <option v-for="m in METRIC_KEYS" :key="m" :value="m">{{ METRIC_LABEL[m] }}</option>
          </select>
        </label>
        <button class="btn btn-secondary" :disabled="loading" @click="reload">查询</button>
        <div class="q-spacer"></div>
        <label class="q-item">
          <span class="q-label">帖子</span>
          <select v-model="postId" class="q-input mono">
            <option v-for="p in DEMO_POST_IDS" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>
        <button class="btn btn-primary" :disabled="loading" @click="doCapture">采集快照</button>
      </div>

      <p v-if="captureMsg" class="notice" :class="`notice--${captureMsg.kind}`">{{ captureMsg.text }}</p>
      <p class="fake-note">
        指标连接器为 Fake（录制 demo 数据，零 live network）——真实平台数据 API 回采属 stop-condition。
        缺失指标一律显示 <span class="mono">—</span>（未采集），绝不当 0。
      </p>

      <!-- Baseline Row -->
      <div class="snapshot-row">
        <div v-for="(snap, i) in baselineCards" :key="i" class="snapshot-card">
          <span class="snap-label">{{ snap.label }}</span>
          <span class="snap-value mono">{{ snap.value }}</span>
          <span class="snap-change mono">{{ snap.note }}</span>
        </div>
      </div>

      <!-- Chart Row -->
      <div class="chart-row">
        <div class="chart-card">
          <div class="chart-header">
            <h3 class="panel-title">账号内相对表现（分组中位数 / 基线）</h3>
            <span class="hint">min_samples = {{ dashboard.data.value?.dashboard.min_samples ?? "—" }}</span>
          </div>
          <StateBlock v-if="dashboard.loading.value" kind="loading" title="正在拉取效果看板…" />
          <StateBlock
            v-else-if="dashboard.error.value"
            kind="error"
            :title="dashboard.offline.value ? '无法连接控制面 API' : '效果看板拉取失败'"
            :detail="dashboard.error.value"
          />
          <StateBlock
            v-else-if="rankedGroups.length === 0"
            kind="empty"
            :title="`没有可排序的分组：已拉取 ${dashboard.data.value?.record_count ?? 0} 条记录，样本足够的分组为 0（样本不足的分组见下方折叠区）。`"
          />
          <div v-else class="platform-list">
            <div v-for="g in rankedGroups" :key="g.dimension + g.value" class="platform-item">
              <span class="platform-name">{{ DIMENSION_LABEL[g.dimension] }} · {{ g.value }}</span>
              <div class="platform-bar-track">
                <div class="platform-bar-fill" :style="{ width: barWidth(g.median_relative), background: '#00FFFF' }"></div>
              </div>
              <span class="platform-percent mono">{{ relText(g.median_relative) }}</span>
              <span class="platform-count mono">n={{ g.sample_count }}</span>
            </div>
          </div>

          <!-- 样本不足折叠区：不排序 -->
          <div class="insufficient">
            <button class="link-btn" @click="showInsufficient = !showInsufficient">
              样本不足分组（{{ insufficientGroups.length }}）{{ showInsufficient ? "收起" : "展开" }} · 不参与排序
            </button>
            <div v-if="showInsufficient" class="insufficient-list">
              <span v-for="g in insufficientGroups" :key="g.dimension + g.value" class="insufficient-item mono">
                {{ DIMENSION_LABEL[g.dimension] }}·{{ g.value }} (n={{ g.sample_count }})
              </span>
              <span v-if="insufficientGroups.length === 0" class="insufficient-item mono">—</span>
            </div>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-header">
            <h3 class="panel-title">学习信号</h3>
          </div>
          <p class="hint">文案口径：X 与 Y <strong>相关（非因果）</strong>——后端 association_only 恒为真。</p>
          <StateBlock v-if="learning.loading.value" kind="loading" title="正在拉取学习信号…" />
          <StateBlock v-else-if="learning.error.value" kind="error" title="学习信号拉取失败" :detail="learning.error.value" />
          <StateBlock
            v-else-if="(learning.data.value?.report.signals?.length ?? 0) === 0"
            kind="empty"
            :title="`没有信号结果：已拉取 ${learning.data.value?.record_count ?? 0} 条记录。`"
          />
          <div v-else class="signal-list">
            <div v-for="s in learning.data.value?.report.signals ?? []" :key="s.signal" class="signal-item">
              <div class="signal-head">
                <span class="signal-name">{{ s.signal }}</span>
                <StatusBadge :variant="directionVariant(s.direction)" :label="DIRECTION_LABEL[s.direction]" />
              </div>
              <span class="signal-body mono">
                秩相关 {{ s.correlation == null ? "—" : s.correlation.toFixed(3) }} · n={{ s.sample_count }}
              </span>
              <span class="signal-note">
                {{ s.signal }} 与 {{ METRIC_LABEL[s.metric] }} {{ DIRECTION_LABEL[s.direction] }}（相关，非因果）
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Snapshots -->
      <div class="bottom-row">
        <div class="table-card">
          <div class="table-card-header">
            <h3 class="panel-title">快照序列 · {{ postId }}</h3>
          </div>
          <StateBlock v-if="snapshots.error.value" kind="error" title="快照拉取失败" :detail="snapshots.error.value" />
          <StateBlock
            v-else-if="snapshotRows.length === 0"
            kind="empty"
            title="该帖子还没有快照：已成功拉取，尚无采集记录。点右上「采集快照」。"
          />
          <DataTable v-else :columns="columns" :rows="snapshotRows" hoverable>
            <template #cell-age="{ value }"><span class="mono">{{ value }}</span></template>
            <template #cell-views="{ value }"><span class="mono">{{ value }}</span></template>
            <template #cell-likes="{ value }"><span class="mono">{{ value }}</span></template>
            <template #cell-completion="{ value }"><span class="mono">{{ value }}</span></template>
            <template #cell-saves="{ value }"><span class="mono dim">{{ value }}</span></template>
            <template #cell-observedAt="{ value }"><span class="mono dim">{{ value }}</span></template>
          </DataTable>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import AppLayout from "@/components/AppLayout.vue";
import DataTable from "@/components/DataTable.vue";
import StateBlock from "@/components/StateBlock.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import { useAsync } from "@/composables/useAsync";
import { errorText } from "@/api/client";
import {
  captureSnapshot,
  DEMO_ACCOUNT_ID,
  DEMO_POST_IDS,
  DIMENSION_LABEL,
  DIRECTION_LABEL,
  getDashboard,
  getLearningReport,
  listSnapshots,
  METRIC_LABEL,
  metricText,
  type DashboardResponse,
  type LearningResponse,
  type MetricField,
  type PerformanceSnapshot,
  type SignalDirection,
} from "@/api/performance";
import type { PublishPlatform } from "@/api/publish";
import { datetime } from "@/utils/format";

type Variant = "success" | "warning" | "error" | "info" | "neutral";

const METRIC_KEYS = Object.keys(METRIC_LABEL) as MetricField[];

const dashboard = useAsync<DashboardResponse>();
const learning = useAsync<LearningResponse>();
const snapshots = useAsync<PerformanceSnapshot[]>();

const q = reactive({
  account_id: DEMO_ACCOUNT_ID,
  platform: "TIKTOK" as PublishPlatform,
  age_hours: 24,
  metric: "VIEWS" as MetricField,
});

const postId = ref<string>(DEMO_POST_IDS[0]);
const showInsufficient = ref(false);
const captureMsg = ref<{ kind: "ok" | "warn" | "error"; text: string } | null>(null);

const loading = computed(() => dashboard.loading.value || learning.loading.value || snapshots.loading.value);

const rankedGroups = computed(() => dashboard.data.value?.ranked_groups ?? []);
const insufficientGroups = computed(() => dashboard.data.value?.insufficient_groups ?? []);

const baselineCards = computed(() => {
  const base = dashboard.data.value?.dashboard.baseline;
  return [
    { label: "记录数", value: String(dashboard.data.value?.record_count ?? 0), note: "账号内" },
    { label: `基线中位数 · ${METRIC_LABEL[q.metric]}`, value: metricText(base?.median ?? null), note: `n=${base?.sample_count ?? 0}` },
    { label: "P25", value: metricText(base?.p25 ?? null), note: "" },
    { label: "P75", value: metricText(base?.p75 ?? null), note: "" },
    { label: "可排序分组", value: String(rankedGroups.value.length), note: `样本不足 ${insufficientGroups.value.length}` },
  ];
});

const columns = [
  { key: "age", label: "时龄(h)", width: "90px", align: "right" as const },
  { key: "views", label: "播放量", width: "120px", align: "right" as const },
  { key: "likes", label: "点赞", width: "100px", align: "right" as const },
  { key: "completion", label: "完播率", width: "100px", align: "right" as const },
  { key: "saves", label: "收藏", width: "100px", align: "right" as const },
  { key: "observedAt", label: "观测时间", flex: "1" },
];

const snapshotRows = computed(() =>
  (snapshots.data.value ?? []).map((s) => ({
    age: s.age_hours,
    views: metricText(s.views),
    likes: metricText(s.likes),
    completion: s.completion_rate == null ? "—" : `${(s.completion_rate * 100).toFixed(1)}%`,
    saves: metricText(s.saves),
    observedAt: datetime(s.observed_at),
  })),
);

function relText(v: number | null | undefined): string {
  return v == null ? "—" : `${(v * 100).toFixed(0)}%`;
}

function barWidth(v: number | null | undefined): string {
  if (v == null) return "0%";
  return `${Math.max(0, Math.min(100, v * 50))}%`;
}

function directionVariant(d: SignalDirection): Variant {
  if (d === "POSITIVE") return "success";
  if (d === "NEGATIVE") return "warning";
  if (d === "INSUFFICIENT") return "neutral";
  return "info";
}

async function reload(): Promise<void> {
  await Promise.all([
    dashboard.run(() => getDashboard({ ...q })),
    learning.run(() => getLearningReport({ ...q })),
    snapshots.run(() => listSnapshots(postId.value)),
  ]);
}

async function doCapture(): Promise<void> {
  captureMsg.value = null;
  try {
    const res = await captureSnapshot({
      account_id: q.account_id,
      platform: q.platform,
      post_id: postId.value,
      age_hours: q.age_hours,
    });
    captureMsg.value = {
      kind: res.created ? "ok" : "warn",
      text: res.created
        ? `已采集快照 ${res.snapshot.id}（缺失指标保持 null）`
        : `该 (帖子, 时龄) 已有快照，未重复写入：${res.snapshot.id}`,
    };
    await snapshots.run(() => listSnapshots(postId.value));
  } catch (err) {
    // 404 = 录制里没有这个 (post, age)；429 = 限流（detail 带 retry_after_seconds）
    captureMsg.value = { kind: "error", text: `采集失败：${errorText(err)}` };
  }
}

onMounted(reload);
</script>

<style scoped>
.stats-view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

.fake-note {
  font-size: var(--font-size-xs);
  color: var(--color-status-warning);
  background: rgba(245, 166, 35, 0.08);
  border: 1px solid rgba(245, 166, 35, 0.3);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  line-height: 1.6;
}

.notice {
  font-size: var(--font-size-base);
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-primary);
  line-height: 1.6;
}

.notice--warn {
  color: var(--color-status-warning);
  border-color: rgba(245, 166, 35, 0.4);
}

.notice--error {
  color: var(--color-status-error);
  border-color: rgba(239, 68, 68, 0.4);
}

/* ===== Query bar ===== */
.query-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.q-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.q-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.q-input {
  height: 30px;
  padding: 0 8px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: var(--font-size-xs);
  font-family: inherit;
  outline: none;
}

.q-spacer {
  flex: 1;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  padding: 0 14px;
  font-size: var(--font-size-sm);
  font-weight: 500;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms ease;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--color-accent-primary);
  color: #fff;
}

.btn-secondary {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-strong);
  color: var(--color-text-primary);
}

/* ===== Baseline Row ===== */
.snapshot-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}

.snapshot-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.snap-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.snap-value {
  font-size: var(--font-size-4xl);
  font-weight: 700;
  color: var(--color-text-primary);
}

.snap-change {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* ===== Chart Row ===== */
.chart-row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
}

.chart-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

/* ===== Group list ===== */
.platform-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.platform-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.platform-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  min-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-bar-track {
  flex: 1;
  height: 8px;
  background: var(--color-bg-elevated);
  border-radius: 4px;
  overflow: hidden;
}

.platform-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 500ms ease;
}

.platform-percent {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  font-weight: 600;
  min-width: 56px;
  text-align: right;
}

.platform-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  min-width: 44px;
  text-align: right;
}

.insufficient {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border-subtle);
}

.link-btn {
  background: transparent;
  color: var(--color-accent-primary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  text-align: left;
}

.insufficient-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.insufficient-item {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  padding: 4px 8px;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-sm);
}

/* ===== Signals ===== */
.signal-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.signal-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
}

.signal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.signal-name {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.signal-body {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.signal-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.5;
}

/* ===== Bottom Row ===== */
.bottom-row {
  display: flex;
  gap: 16px;
}

.table-card {
  flex: 1;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.table-card-header {
  padding: 20px 20px 0;
}

.mono.dim {
  color: var(--color-text-tertiary);
}
</style>
