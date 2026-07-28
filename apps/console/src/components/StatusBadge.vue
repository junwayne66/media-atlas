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
  font-family: var(--font-family-mono);
  letter-spacing: 0.035em;
  background: rgba(32, 32, 48, 0.6);
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
  background: rgba(0, 32, 16, 0.8);
}

.status-success .status-dot {
  background: var(--color-status-success);
  box-shadow: var(--glow-green);
}

.status-warning {
  color: var(--color-status-warning);
  background: rgba(48, 40, 0, 0.8);
}

.status-warning .status-dot {
  background: var(--color-status-warning);
  box-shadow: 0 0 5px rgba(255, 215, 0, 0.5);
}

.status-error {
  color: var(--color-status-error);
  background: rgba(48, 0, 16, 0.8);
}

.status-error .status-dot {
  background: var(--color-status-error);
}

.status-info {
  color: var(--color-status-info);
  background: rgba(0, 32, 48, 0.8);
}

.status-info .status-dot {
  background: var(--color-status-info);
  box-shadow: var(--glow-cyan-sm);
}

.status-neutral {
  color: var(--color-status-neutral);
}

.status-neutral .status-dot {
  background: var(--color-status-neutral);
}
</style>
