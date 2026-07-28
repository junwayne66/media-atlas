<template>
  <AppLayout>
    <main class="settings-view">
      <header class="page-heading">
        <div>
          <h1>设置</h1>
          <p>本地控制面配置；真实 Provider 与平台联网在此版本保持禁用。</p>
        </div>
        <button type="button" class="btn btn-secondary" :disabled="settings.loading.value" @click="refreshSettings">
          {{ settings.loading.value ? "刷新中…" : "刷新设置" }}
        </button>
      </header>

      <StateBlock
        v-if="settings.loading.value && !settings.data.value"
        kind="loading"
        title="正在读取本地设置…"
      />
      <StateBlock
        v-else-if="settings.error.value && !settings.data.value"
        kind="error"
        title="设置读取失败"
        :detail="settings.error.value"
      />
      <VaultPanel
        v-else-if="settings.data.value"
        :vault="settings.data.value.vault"
        @changed="refreshSettings"
      />

      <div
        class="settings-tabs"
        role="tablist"
        aria-label="设置分类"
      >
        <button
          v-for="(tab, index) in tabs"
          :id="`settings-tab-${tab.key}`"
          :key="tab.key"
          class="settings-tab"
          :class="{ active: tab.key === activeTab }"
          role="tab"
          :aria-selected="tab.key === activeTab"
          :aria-controls="`settings-panel-${tab.key}`"
          :tabindex="tab.key === activeTab ? 0 : -1"
          type="button"
          @click="activeTab = tab.key"
          @keydown="onTabKeydown($event, index)"
        >
          {{ tab.label }}
        </button>
      </div>

      <section
        v-show="activeTab === 'providers'"
        id="settings-panel-providers"
        role="tabpanel"
        aria-labelledby="settings-tab-providers"
      >
        <ProviderSettingsPanel
          v-if="settings.data.value"
          :providers="settings.data.value.providers"
          :vault-unlocked="settings.data.value.vault.unlocked"
          @reload="refreshSettings"
        />
      </section>

      <section
        v-show="activeTab === 'accounts'"
        id="settings-panel-accounts"
        role="tabpanel"
        aria-labelledby="settings-tab-accounts"
      >
        <PlatformAccountsPanel
          v-if="settings.data.value"
          :accounts="settings.data.value.accounts"
          :vault-unlocked="settings.data.value.vault.unlocked"
          @reload="refreshSettings"
        />
      </section>

      <section
        v-show="activeTab === 'workers'"
        id="settings-panel-workers"
        class="settings-card"
        role="tabpanel"
        aria-labelledby="settings-tab-workers"
      >
        <div class="card-header">
          <h2>Worker 任务</h2>
          <span class="security-note">后端只提供按 task_id 单查 + 人工 requeue</span>
        </div>

        <div class="task-form">
          <label class="sr-only" for="worker-task-id">Worker task ID</label>
          <input
            id="worker-task-id"
            v-model="taskId"
            class="form-input mono"
            type="text"
            placeholder="worker task id"
            @keyup.enter="lookup"
          />
          <button
            type="button"
            class="btn btn-sm btn-secondary"
            :disabled="!taskId || task.loading.value"
            @click="lookup"
          >
            查询
          </button>
          <button
            type="button"
            class="btn btn-sm btn-danger"
            :disabled="!canRequeue || requeueing"
            :title="canRequeue ? '把终态 FAILED 的任务重新入队（幂等）' : '只有终态 FAILED 的任务可以人工恢复'"
            @click="doRequeue"
          >
            {{ requeueing ? "恢复中…" : "人工 requeue" }}
          </button>
        </div>

        <StateBlock v-if="!task.loaded.value" kind="empty" title="输入 task_id 查询任务状态。" />
        <StateBlock
          v-else-if="task.notFound.value"
          kind="empty"
          title="没有这个 task：已成功查询，后端无该记录。"
          :detail="task.error.value"
        />
        <StateBlock
          v-else-if="task.error.value"
          kind="error"
          title="任务状态查询失败"
          :detail="task.error.value"
        />
        <div v-else-if="task.data.value" class="sys-list">
          <div class="sys-row">
            <span class="sys-label">状态</span>
            <StatusBadge :variant="taskVariant" :label="task.data.value.status" />
          </div>
          <div class="sys-row">
            <span class="sys-label">能力</span>
            <span class="sys-value mono">{{ task.data.value.capability }}</span>
          </div>
          <div class="sys-row">
            <span class="sys-label">尝试次数</span>
            <span class="sys-value mono">
              {{ task.data.value.attempt }} / {{ task.data.value.max_attempts }}
            </span>
          </div>
          <div class="sys-row">
            <span class="sys-label">承租 worker</span>
            <span class="sys-value mono">{{ text(task.data.value.leased_by) }}</span>
          </div>
          <div class="sys-row">
            <span class="sys-label">租约到期</span>
            <span class="sys-value mono">{{ datetime(task.data.value.lease_expires_at) }}</span>
          </div>
          <div class="sys-row">
            <span class="sys-label">输出摘要</span>
            <span class="sys-value mono break">{{ text(task.data.value.output_digest) }}</span>
          </div>
        </div>
        <p v-if="requeueMsg" class="msg-line" aria-live="polite">{{ requeueMsg }}</p>
      </section>

      <section
        v-show="activeTab === 'system'"
        id="settings-panel-system"
        class="settings-card"
        role="tabpanel"
        aria-labelledby="settings-tab-system"
      >
        <h2>系统信息</h2>
        <StateBlock
          v-if="health.error.value"
          kind="error"
          title="健康探测失败"
          :detail="health.error.value"
        />
        <div v-else class="sys-list">
          <div class="sys-row">
            <span class="sys-label">服务</span>
            <span class="sys-value mono">{{ text(health.data.value?.service) }}</span>
          </div>
          <div class="sys-row">
            <span class="sys-label">版本</span>
            <span class="sys-value mono">{{ text(health.data.value?.version) }}</span>
          </div>
          <div class="sys-row">
            <span class="sys-label">健康状态</span>
            <span class="sys-value mono">{{ text(health.data.value?.status) }}</span>
          </div>
          <div class="sys-row">
            <span class="sys-label">API base</span>
            <span class="sys-value mono">{{ API_BASE }}</span>
          </div>
          <div class="sys-row">
            <span class="sys-label">真实外部连接</span>
            <span class="sys-value mono">
              {{ settings.data.value?.live_connections_enabled ? "已启用" : "已禁用" }}
            </span>
          </div>
        </div>
      </section>

      <section
        v-show="activeTab === 'manifest'"
        id="settings-panel-manifest"
        class="settings-card"
        role="tabpanel"
        aria-labelledby="settings-tab-manifest"
      >
        <h2>第三方依赖清单</h2>
        <StateBlock
          kind="unconfigured"
          title="third_party_manifest 只读端点尚未落地。"
          detail="清单目前只在仓库 third_party_manifest.yaml 中维护；新增的 Argon2id 与 AES-GCM 库已登记为 L0。"
        />
      </section>
    </main>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { API_BASE, errorText } from "@/api/client";
import { getHealth, type HealthResponse } from "@/api/health";
import { getSettings, type SettingsSnapshot } from "@/api/settings";
import { getWorkerTask, requeueWorkerTask, type WorkerTaskStatus } from "@/api/workers";
import AppLayout from "@/components/AppLayout.vue";
import PlatformAccountsPanel from "@/components/settings/PlatformAccountsPanel.vue";
import ProviderSettingsPanel from "@/components/settings/ProviderSettingsPanel.vue";
import VaultPanel from "@/components/settings/VaultPanel.vue";
import StateBlock from "@/components/StateBlock.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import { useAsync } from "@/composables/useAsync";
import { datetime, text } from "@/utils/format";

type Variant = "success" | "warning" | "error" | "info" | "neutral";
type TabKey = "providers" | "accounts" | "workers" | "system" | "manifest";

const tabs: { key: TabKey; label: string }[] = [
  { key: "providers", label: "AI Providers" },
  { key: "accounts", label: "平台账号" },
  { key: "workers", label: "Worker 任务" },
  { key: "system", label: "系统信息" },
  { key: "manifest", label: "第三方清单" },
];

const activeTab = ref<TabKey>("providers");
const taskId = ref("");
const requeueing = ref(false);
const requeueMsg = ref<string | null>(null);
const health = useAsync<HealthResponse>();
const task = useAsync<WorkerTaskStatus>();
const settings = useAsync<SettingsSnapshot>();

const taskVariant = computed<Variant>(() => {
  const state = task.data.value?.status;
  if (!state) return "neutral";
  if (state === "FAILED") return "error";
  if (state === "COMPLETED") return "success";
  if (state === "LEASED" || state === "RUNNING") return "info";
  return "neutral";
});

const canRequeue = computed(() => task.data.value?.status === "FAILED");

async function refreshSettings(): Promise<void> {
  await settings.run(() => getSettings());
}

async function lookup(): Promise<void> {
  requeueMsg.value = null;
  await task.run(() => getWorkerTask(taskId.value.trim()));
}

async function doRequeue(): Promise<void> {
  requeueing.value = true;
  requeueMsg.value = null;
  try {
    await requeueWorkerTask(taskId.value.trim());
    requeueMsg.value = "已重新入队（幂等）。";
    await lookup();
  } catch (err) {
    requeueMsg.value = `requeue 失败：${errorText(err)}`;
  } finally {
    requeueing.value = false;
  }
}

async function onTabKeydown(event: KeyboardEvent, index: number): Promise<void> {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  let next = index;
  if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
  if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
  if (event.key === "Home") next = 0;
  if (event.key === "End") next = tabs.length - 1;
  activeTab.value = tabs[next].key;
  await nextTick();
  document.getElementById(`settings-tab-${tabs[next].key}`)?.focus();
}

onMounted(async () => {
  await Promise.all([health.run(() => getHealth()), refreshSettings()]);
});
</script>

<style scoped>
.settings-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
  padding: 24px;
}

.page-heading,
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

h1 {
  font-size: var(--font-size-2xl);
}

h2 {
  font-size: var(--font-size-xl);
}

.page-heading p,
.security-note {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.settings-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
}

.settings-tab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  min-height: 34px;
  padding: 0 14px;
  color: var(--color-text-secondary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: 500;
}

.settings-tab:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.settings-tab.active {
  color: var(--color-text-primary);
  border: 1px solid var(--color-accent-primary);
  background: var(--color-bg-elevated);
}

.settings-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-card);
}

.task-form {
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 8px;
  color: var(--color-text-primary);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 14px;
  color: var(--color-text-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 600;
  white-space: nowrap;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-sm {
  min-height: 30px;
  padding: 0 10px;
  font-size: var(--font-size-xs);
}

.btn-secondary {
  border: 1px solid var(--color-border-strong);
  background: var(--color-bg-elevated);
}

.btn-danger {
  color: var(--color-status-error);
  border: 1px solid color-mix(in srgb, var(--color-status-error) 35%, transparent);
  background: color-mix(in srgb, var(--color-status-error) 9%, transparent);
}

.sys-list {
  display: flex;
  flex-direction: column;
}

.sys-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.sys-row:last-child {
  border-bottom: none;
}

.sys-label {
  color: var(--color-text-secondary);
}

.sys-value {
  color: var(--color-text-primary);
  font-weight: 500;
}

.break,
.msg-line {
  word-break: break-all;
}

.msg-line {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 900px) {
  .settings-view {
    padding: 16px;
  }

  .page-heading,
  .card-header,
  .task-form {
    align-items: stretch;
    flex-direction: column;
  }

  .sys-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
