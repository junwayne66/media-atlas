<script setup lang="ts">
defineProps<{ stage: string }>();

const COLORS: Record<string, string> = {
  EMERGING: "#6b7280",
  RISING: "#0a7d33",
  PEAK: "#b45309",
  SATURATED: "#7c3aed",
  DECAYING: "#b3261e",
  ARCHIVED: "#9ca3af",
};
</script>

<template>
  <span class="badge" :style="{ background: COLORS[stage] ?? '#6b7280' }">{{ stage }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 10px;
  color: white;
  font-size: 0.75rem;
  font-weight: 600;
}
</style>
