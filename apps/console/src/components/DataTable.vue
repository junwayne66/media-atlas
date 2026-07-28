<template>
  <div class="data-table">
    <!-- Header -->
    <div class="table-header">
      <div
        v-for="col in columns"
        :key="col.key"
        class="table-cell table-cell--header"
        :style="{ width: col.width, flex: col.flex || 'none', textAlign: col.align || 'left' }"
      >
        {{ col.label }}
      </div>
    </div>

    <!-- Rows -->
    <div
      v-for="(row, index) in rows"
      :key="index"
      class="table-row"
      :class="{ 'table-row--hover': hoverable }"
    >
      <div
        v-for="col in columns"
        :key="col.key"
        class="table-cell"
        :style="{ width: col.width, flex: col.flex || 'none', textAlign: col.align || 'left' }"
      >
        <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
          {{ row[col.key] }}
        </slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface TableColumn {
  key: string;
  label: string;
  width?: string;
  flex?: string;
  align?: "left" | "center" | "right";
}

defineProps<{
  columns: TableColumn[];
  rows: Record<string, any>[];
  hoverable?: boolean;
}>();
</script>

<style scoped>
.data-table {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.table-header {
  display: flex;
  align-items: center;
  height: 40px;
  background: rgba(0, 255, 255, 0.035);
  border-bottom: 1px solid var(--color-border-subtle);
  flex-shrink: 0;
}

.table-row {
  display: flex;
  align-items: center;
  min-height: 52px;
  border-bottom: 1px solid var(--color-border-subtle);
  transition: background 150ms ease;
}

.table-row--hover:hover {
  background: rgba(0, 255, 255, 0.035);
}

.table-row:last-child {
  border-bottom: none;
}

.table-cell {
  padding: 0 16px;
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
}

.table-cell--header {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-accent-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
</style>
