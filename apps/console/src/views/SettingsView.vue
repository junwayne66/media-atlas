<template>
  <AppLayout>
    <div class="settings-view">
      <!-- Settings Tabs -->
      <div class="settings-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="settings-tab"
          :class="{ active: tab.key === activeTab }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Worker 队列（唯一已接入的设置域） -->
      <div v-show="activeTab === 'workers'" class="provider-card">
        <div class="provider-header">
          <h3 class="panel-title">Worker 任务</h3>
          <span class="security-note">后端只提供按 task_id 单查 + 人工 requeue，没有队列列表端点</span>
        </div>

        <div class="task-form">
          <input
            v-model="taskId"
            class="form-input mono"
            type="text"
            placeholder="worker task id"
            @keyup.enter="lookup"
          />
          <button class="btn btn-sm btn-secondary" :disabled="!taskId || task.loading.value" @click="lookup">查询</button>
          <button
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
        <StateBlock v-else-if="task.error.value" kind="error" title="任务状态查询失败" :detail="task.error.value" />
        <div v-else-if="task.data.value" class="sys-list">
          <div class="sys-row">
            <span class="sys-label">状态</span>
            <span class="sys-value">
              <StatusBadge :variant="taskVariant" :label="task.data.value.status" />
            </span>
          </div>
          <div class="sys-row"><span class="sys-label">能力</span><span class="sys-value mono">{{ task.data.value.capability }}</span></div>
          <div class="sys-row">
            <span class="sys-label">尝试次数</span>
            <span class="sys-value mono">{{ task.data.value.attempt }} / {{ task.data.value.max_attempts }}</span>
          </div>
          <div class="sys-row"><span class="sys-label">承租 worker</span><span class="sys-value mono">{{ text(task.data.value.leased_by) }}</span></div>
          <div class="sys-row"><span class="sys-label">租约到期</span><span class="sys-value mono">{{ datetime(task.data.value.lease_expires_at) }}</span></div>
          <div class="sys-row"><span class="sys-label">输出摘要</span><span class="sys-value mono break">{{ text(task.data.value.output_digest) }}</span></div>
        </div>
        <p v-if="requeueMsg" class="msg-line">{{ requeueMsg }}</p>
      </div>

      <!-- 系统信息：只展示后端真实上报的字段 -->
      <div v-show="activeTab === 'system'" class="system-card">
        <h3 class="panel-title">系统信息</h3>
        <StateBlock v-if="health.error.value" kind="error" title="健康探测失败" :detail="health.error.value" />
        <div v-else class="sys-list">
          <div class="sys-row"><span class="sys-label">服务</span><span class="sys-value mono">{{ text(health.data.value?.service) }}</span></div>
          <div class="sys-row"><span class="sys-label">版本</span><span class="sys-value mono">{{ text(health.data.value?.version) }}</span></div>
          <div class="sys-row"><span class="sys-label">健康状态</span><span class="sys-value mono">{{ text(health.data.value?.status) }}</span></div>
          <div class="sys-row"><span class="sys-label">API base</span><span class="sys-value mono">{{ API_BASE }}</span></div>
          <div class="sys-row">
            <span class="sys-label">运行时间 / 存储用量 / 队列深度</span>
            <span class="sys-value mono">未接入</span>
          </div>
        </div>
        <p class="security-note">运行时间、存储用量、队列深度暂无后端端点——这里不摆估算值。</p>
      </div>

      <!-- 未接入的设置域：诚实标注，不摆假数据 -->
      <div v-show="activeTab === 'providers'" class="provider-card">
        <div class="provider-header">
          <h3 class="panel-title">Provider 注册表 / 账号凭据</h3>
          <span class="security-note">凭据只以不透明 handle 存在，界面永不展示明文</span>
        </div>
        <StateBlock
          kind="unconfigured"
          title="Provider 注册表与账号管理端点尚未落地（docs/modules/45 §11 标记为 📋 计划）。"
          detail="接入后这里展示：连接器能力、kill-switch、熔断器状态、PlatformAccount 的 credential_ref handle 摘要。"
        />
      </div>

      <div v-show="activeTab === 'manifest'" class="manifest-card">
        <h3 class="panel-title">第三方依赖清单</h3>
        <StateBlock
          kind="unconfigured"
          title="third_party_manifest 只读端点尚未落地。"
          detail="清单目前只在仓库 third_party_manifest.yaml 中维护（含 L0–L4 许可隔离级）。"
        />
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import AppLayout from "@/components/AppLayout.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import StateBlock from "@/components/StateBlock.vue";
import { useAsync } from "@/composables/useAsync";
import { API_BASE, errorText } from "@/api/client";
import { getHealth, type HealthResponse } from "@/api/health";
import { getWorkerTask, requeueWorkerTask, type WorkerTaskStatus } from "@/api/workers";
import { datetime, text } from "@/utils/format";

type Variant = "success" | "warning" | "error" | "info" | "neutral";

const tabs = [
  { key: "workers", label: "Worker 任务" },
  { key: "system", label: "系统信息" },
  { key: "providers", label: "Provider / 账号" },
  { key: "manifest", label: "第三方清单" },
];

const activeTab = ref("workers");
const taskId = ref("");
const requeueing = ref(false);
const requeueMsg = ref<string | null>(null);

const health = useAsync<HealthResponse>();
const task = useAsync<WorkerTaskStatus>();

const taskVariant = computed<Variant>(() => {
  const s = task.data.value?.status;
  if (!s) return "neutral";
  if (s === "FAILED") return "error";
  if (s === "COMPLETED") return "success";
  if (s === "LEASED" || s === "RUNNING") return "info";
  return "neutral";
});

const canRequeue = computed(() => task.data.value?.status === "FAILED");

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

onMounted(async () => {
  await health.run(() => getHealth());
});
</script>

<style scoped>
.settings-view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

/* ===== Settings Tabs ===== */
.settings-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
}

.settings-tab {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  padding: 0 14px;
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms ease;
}

.settings-tab:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.settings-tab.active {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-accent-primary);
  color: var(--color-text-primary);
}

/* ===== Cards ===== */
.provider-card,
.system-card,
.manifest-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.provider-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.security-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

.task-form {
  display: flex;
  gap: 8px;
  align-items: center;
}

.form-input {
  flex: 1;
  min-width: 0;
  height: 30px;
  padding: 0 8px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: var(--font-size-xs);
  font-family: inherit;
  outline: none;
}

.msg-line {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  line-height: 1.6;
  word-break: break-all;
}

.sys-list {
  display: flex;
  flex-direction: column;
  gap: 0;
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
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
}

.sys-value {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  font-weight: 500;
}

.break {
  word-break: break-all;
}

/* ===== Buttons ===== */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 34px;
  padding: 0 16px;
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

.btn-sm {
  height: 30px;
  padding: 0 10px;
  font-size: var(--font-size-xs);
}

.btn-secondary {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-strong);
  color: var(--color-text-primary);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--color-bg-hover);
}

.btn-danger {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-status-error);
}

.btn-danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
}
</style>
