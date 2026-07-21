<script setup lang="ts">
import { onMounted, ref } from "vue";

interface ApiHealth {
  status: string;
  service: string;
  version: string;
}

const health = ref<ApiHealth | null>(null);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    const resp = await fetch("/api/healthz");
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    health.value = (await resp.json()) as ApiHealth;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
});
</script>

<template>
  <main class="page">
    <h1>VideoForge 控制台</h1>
    <p class="subtitle">热点驱动 · AI 辅助 · 人工可控的多语言视频再创作系统</p>
    <section class="card">
      <h2>控制平面状态</h2>
      <p v-if="health">API 服务正常：{{ health.service }} v{{ health.version }}</p>
      <p v-else-if="error">API 不可用：{{ error }}</p>
      <p v-else>检测中…</p>
    </section>
  </main>
</template>

<style scoped>
.page {
  max-width: 720px;
  margin: 0 auto;
  padding: 3rem 1.5rem;
}

.subtitle {
  color: #666;
}

.card {
  margin-top: 2rem;
  padding: 1rem 1.5rem;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
}
</style>
