<script setup lang="ts">
import { onMounted, ref } from "vue";

import TrendBoard from "./components/TrendBoard.vue";
import TrendDetail from "./components/TrendDetail.vue";

interface ApiHealth {
  status: string;
  service: string;
  version: string;
}

const health = ref<ApiHealth | null>(null);
const selectedId = ref<string | null>(null);
const board = ref<InstanceType<typeof TrendBoard> | null>(null);

onMounted(async () => {
  try {
    const resp = await fetch("/api/healthz");
    if (resp.ok) health.value = (await resp.json()) as ApiHealth;
  } catch {
    health.value = null;
  }
});

function onChanged() {
  board.value?.refresh();
}
</script>

<template>
  <main class="page">
    <header class="app-header">
      <h1>VideoForge 控制台</h1>
      <span v-if="health" class="ok">API {{ health.version }}</span>
      <span v-else class="down">API 不可用</span>
    </header>

    <div class="layout">
      <TrendBoard ref="board" @select="selectedId = $event" />
      <TrendDetail
        v-if="selectedId"
        :cluster-id="selectedId"
        @changed="onChanged"
        @project-created="onChanged"
      />
    </div>
  </main>
</template>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem;
}
.app-header {
  display: flex;
  align-items: baseline;
  gap: 1rem;
}
.layout {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 1rem;
  margin-top: 1rem;
}
.ok {
  color: #0a7d33;
}
.down {
  color: #b3261e;
}
</style>
