<template>
  <AppLayout>
    <div class="localization-view">
      <!-- 诚实标注：本页仍是静态演示稿，本地化端点尚未落地（docs/modules/45 §11 标记 📋 计划） -->
      <div class="demo-banner">
        <span class="demo-badge">演示数据</span>
        <span class="demo-text">
          本页展示的是交互演示稿，<strong>不是真实数据</strong>——本地化工作台端点（变体 / 句级审批 / 重跑作用域）
          随后端本地化 workflow 落地后接入。
        </span>
      </div>

      <!-- Variant Bar -->
      <div class="variant-bar">
        <button v-for="v in variants" :key="v.key" class="variant-item" :class="{ active: v.key === 'zh-TW' }">
          {{ v.label }}
        </button>
      </div>

      <!-- Sentence Editor -->
      <div class="sentence-card">
        <div class="sentence-header">
          <div>
            <h3 class="panel-title">句子编辑 · #03</h3>
            <span class="timecode mono">00:00:20 → 00:00:35</span>
          </div>
          <StatusBadge variant="warning" label="BLOCKER 待确认" />
        </div>

        <div class="sentence-body">
          <div class="sentence-row">
            <div class="sentence-label">原文 (zh-CN)</div>
            <div class="sentence-text">第二个技巧：建设性反馈。用"我观察到..."而不是"你总是..."来表达不满。</div>
          </div>
          <div class="sentence-row">
            <div class="sentence-label">变体 (zh-TW)</div>
            <div class="sentence-text sentence-editable">第二個技巧：建設性反饋。用「我觀察到...」而不是「你總是...」來表達不滿。</div>
          </div>
        </div>

        <div class="sentence-footer">
          <div class="blocker-note">
            <span class="blocker-label">BLOCKER 句子:</span>
            <span class="blocker-text">「你总是」在繁体中文语境中可能过于直接，建议调整为「你經常」</span>
          </div>
          <div class="sentence-actions">
            <button class="btn btn-secondary" disabled>批准 (禁用)</button>
            <button class="btn btn-warning">标记 BLOCKER</button>
          </div>
        </div>
      </div>

      <!-- Subtitle Preview -->
      <div class="subtitle-card">
        <h3 class="panel-title">字幕预览</h3>
        <div class="subtitle-preview">
          <div v-for="(sub, i) in subtitles" :key="i" class="subtitle-item" :class="{ 'sub-current': i === 2 }">
            <span class="sub-time mono">{{ sub.time }}</span>
            <span class="sub-text">{{ sub.text }}</span>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import AppLayout from "@/components/AppLayout.vue";
import StatusBadge from "@/components/StatusBadge.vue";

const variants = [
  { key: "zh-CN", label: "简体中文" },
  { key: "zh-TW", label: "繁体中文" },
  { key: "en-US", label: "English" },
  { key: "ja-JP", label: "日本語" },
];

const subtitles = [
  { time: "00:00:00", text: "在職場中，溝通不僅僅是表達，更是傾聽和理解的過程。" },
  { time: "00:00:08", text: "第一個技巧：主動傾聽。不要急於打斷對方。" },
  { time: "00:00:20", text: "第二個技巧：建設性反饋。用「我觀察到...」而不是「你總是...」。" },
  { time: "00:00:35", text: "第三個技巧：共情理解。站在對方的角度思考問題。" },
  { time: "00:00:45", text: "記住這三個技巧：傾聽、反饋、共情。" },
];
</script>

<style scoped>
.localization-view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow: hidden;
}

.demo-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(245, 166, 35, 0.08);
  border: 1px solid rgba(245, 166, 35, 0.3);
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.demo-badge {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: var(--radius-sm);
  background: rgba(245, 166, 35, 0.18);
  color: var(--color-status-warning);
  font-size: var(--font-size-xs);
  font-weight: 600;
  flex-shrink: 0;
}

.demo-text {
  font-size: var(--font-size-xs);
  color: var(--color-status-warning);
  line-height: 1.6;
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

/* ===== Variant Bar ===== */
.variant-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.variant-item {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 34px;
  padding: 0 16px;
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms ease;
}

.variant-item:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.variant-item.active {
  background: var(--color-bg-elevated);
  border-color: var(--color-accent-primary);
  color: var(--color-text-primary);
}

/* ===== Sentence Card ===== */
.sentence-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.sentence-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 20px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.timecode {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.sentence-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sentence-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sentence-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.sentence-text {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  line-height: 1.6;
  padding: 12px 16px;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
}

.sentence-editable {
  border: 1px solid var(--color-border-strong);
}

.sentence-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-top: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
}

.blocker-note {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.blocker-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-status-error);
  text-transform: uppercase;
}

.blocker-text {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
}

.sentence-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 34px;
  padding: 0 14px;
  font-size: var(--font-size-base);
  font-weight: 500;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms ease;
  white-space: nowrap;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-secondary);
}

.btn-warning {
  background: var(--color-status-warning);
  color: #fff;
}

.btn-warning:hover {
  filter: brightness(1.1);
}

/* ===== Subtitle Card ===== */
.subtitle-card {
  flex: 1;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.subtitle-preview {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
}

.subtitle-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  transition: background 150ms ease;
}

.subtitle-item:hover {
  background: var(--color-bg-hover);
}

.sub-current {
  background: rgba(0, 255, 255, 0.08);
  border: 1px solid rgba(0, 255, 255, 0.3);
}

.sub-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  min-width: 80px;
}

.sub-text {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
}
</style>
