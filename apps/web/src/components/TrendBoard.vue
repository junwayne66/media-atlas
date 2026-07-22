<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { listClusters, type TrendCluster } from "../api/trends";
import StageBadge from "./StageBadge.vue";

const emit = defineEmits<{ select: [id: string] }>();

const clusters = ref<TrendCluster[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const stageFilter = ref("");
const verticalFilter = ref("");

const STAGES = ["EMERGING", "RISING", "PEAK", "SATURATED", "DECAYING", "ARCHIVED"];

async function refresh() {
  loading.value = true;
  error.value = null;
  try {
    clusters.value = await listClusters({
      stage: stageFilter.value || undefined,
      vertical: verticalFilter.value || undefined,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

const isEmpty = computed(() => !loading.value && !error.value && clusters.value.length === 0);

function pct(x: number | null): string {
  return x === null ? "—" : `${Math.round(x * 100)}`;
}

defineExpose({ refresh });
onMounted(refresh);
</script>

<template>
  <section class="board">
    <header class="toolbar">
      <h2>热点池</h2>
      <label>
        阶段
        <select v-model="stageFilter" @change="refresh">
          <option value="">全部</option>
          <option v-for="s in STAGES" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <label>
        方向
        <input v-model="verticalFilter" placeholder="如 ai-tech" @keyup.enter="refresh" />
      </label>
      <button @click="refresh">刷新</button>
    </header>

    <p v-if="loading">加载中…</p>
    <p v-else-if="error" class="error">加载失败：{{ error }}</p>
    <p v-else-if="isEmpty" class="empty">暂无热点聚类（可先创建并附加快照）。</p>

    <table v-else class="clusters">
      <thead>
        <tr>
          <th>热度</th>
          <th>标题</th>
          <th>阶段</th>
          <th>成员</th>
          <th>理由码</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="c in clusters"
          :key="c.id"
          class="row"
          data-test="cluster-row"
          @click="emit('select', c.id)"
        >
          <td class="hot">{{ pct(c.hot_score) }}</td>
          <td class="title">{{ c.title }}</td>
          <td><StageBadge :stage="c.stage" /></td>
          <td>{{ c.member_item_ids.length }}</td>
          <td class="codes">
            <span v-for="rc in c.reason_codes.slice(0, 3)" :key="rc" class="code">{{ rc }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.clusters {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
}
.clusters th,
.clusters td {
  text-align: left;
  padding: 0.5rem;
  border-bottom: 1px solid #eee;
}
.row {
  cursor: pointer;
}
.row:hover {
  background: #f6f6ff;
}
.hot {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.code {
  display: inline-block;
  margin-right: 0.3rem;
  padding: 0.05rem 0.4rem;
  background: #eef;
  border-radius: 6px;
  font-size: 0.72rem;
}
.error {
  color: #b3261e;
}
.empty {
  color: #666;
}
</style>
