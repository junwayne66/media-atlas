<template>
  <span class="status-badge" :class="`status-${variant}`">
    <span class="status-dot"></span>
    <span class="status-text">{{ label }}</span>
  </span>
</template>

<script setup lang="ts">
type StatusVariant = "success" | "warning" | "error" | "info" | "neutral";

const props = defineProps<{
  variant: StatusVariant;
  label: string;
}>();

// Use label from prop, not variant
void props;
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 8px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-text {
  line-height: 1;
}

.status-success {
  color: var(--color-status-success);
}

.status-success .status-dot {
  background: var(--color-status-success);
}

.status-warning {
  color: var(--color-status-warning);
}

.status-warning .status-dot {
  background: var(--color-status-warning);
}

.status-error {
  color: var(--color-status-error);
}

.status-error .status-dot {
  background: var(--color-status-error);
}

.status-info {
  color: var(--color-status-info);
}

.status-info .status-dot {
  background: var(--color-status-info);
}

.status-neutral {
  color: var(--color-status-neutral);
}

.status-neutral .status-dot {
  background: var(--color-status-neutral);
}
</style>
