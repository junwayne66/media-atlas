<template>
  <div class="state-block" :class="`state-block--${kind}`">
    <StatusBadge :variant="badgeVariant" :label="badgeLabel" />
    <p class="state-title">{{ title }}</p>
    <p v-if="detail" class="state-detail mono">{{ detail }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
/**
 * 空态 / 错误态 / 未配置态的统一展示块（§0.2 红线 1：三态必须可区分）。
 * 视觉沿用既有 StatusBadge + 卡片内文案样式，不引入新的设计元素。
 */
import { computed } from "vue";
import StatusBadge from "./StatusBadge.vue";

type Kind = "empty" | "error" | "unconfigured" | "loading";

const props = defineProps<{
  kind: Kind;
  title: string;
  detail?: string | null;
}>();

const badgeVariant = computed<"neutral" | "error" | "warning" | "info">(() => {
  switch (props.kind) {
    case "error":
      return "error";
    case "unconfigured":
      return "warning";
    case "loading":
      return "info";
    default:
      return "neutral";
  }
});

const badgeLabel = computed(() => {
  switch (props.kind) {
    case "error":
      return "拉取失败";
    case "unconfigured":
      return "未配置";
    case "loading":
      return "加载中";
    default:
      return "暂无数据";
  }
});
</script>

<style scoped>
.state-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 24px;
  background: var(--color-glass);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: inset 0 0 14px rgba(0, 255, 255, 0.03);
}

.state-title {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  line-height: 1.6;
}

.state-detail {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.6;
  word-break: break-all;
  white-space: pre-wrap;
}

.state-block--error {
  border-color: rgba(255, 51, 102, 0.35);
}

.state-block--unconfigured {
  border-color: rgba(255, 215, 0, 0.3);
}
</style>
