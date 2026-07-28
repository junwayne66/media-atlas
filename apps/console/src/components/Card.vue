<template>
  <div class="card" :class="{ 'card--padded': padded }">
    <div v-if="title || $slots.header" class="card-header">
      <slot name="header">
        <h3 class="card-title">{{ title }}</h3>
      </slot>
      <div v-if="$slots.actions" class="card-actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="card-body">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title?: string;
  padded?: boolean;
}>();
</script>

<style scoped>
.card {
  background: var(--color-glass);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-xl);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  backdrop-filter: blur(28px);
  box-shadow: 0 4px 24px rgba(0, 204, 255, 0.05);
}

.card--padded .card-body {
  padding: var(--space-xl);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-xl) var(--space-xl) 0;
  gap: var(--space-lg);
}

.card-title {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-accent-primary);
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-body {
  flex: 1;
}
</style>
