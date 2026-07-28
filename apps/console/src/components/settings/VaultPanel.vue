<template>
  <section class="vault-panel" aria-labelledby="vault-title">
    <div class="panel-header">
      <div>
        <h2 id="vault-title">本地凭据库</h2>
        <p>口令不落盘；API 重启后自动锁定。服务端密文与 Desktop/Device handle 分开保存。</p>
      </div>
      <StatusBadge :variant="badge.variant" :label="badge.label" />
    </div>

    <form
      v-if="vault.state === 'UNINITIALIZED'"
      class="vault-form"
      @submit.prevent="initialize"
    >
      <label for="vault-new-passphrase">创建口令（至少 12 个字符）</label>
      <input
        id="vault-new-passphrase"
        v-model="passphrase"
        type="password"
        autocomplete="new-password"
        minlength="12"
        maxlength="1024"
        required
      />
      <label for="vault-confirm-passphrase">确认口令</label>
      <input
        id="vault-confirm-passphrase"
        v-model="confirmation"
        type="password"
        autocomplete="new-password"
        minlength="12"
        maxlength="1024"
        required
      />
      <button type="submit" class="btn primary" :disabled="busy">初始化并解锁</button>
    </form>

    <form v-else-if="vault.state === 'LOCKED'" class="vault-form" @submit.prevent="unlock">
      <label for="vault-passphrase">解锁口令</label>
      <input
        id="vault-passphrase"
        v-model="passphrase"
        type="password"
        autocomplete="current-password"
        maxlength="1024"
        required
      />
      <button type="submit" class="btn primary" :disabled="busy">解锁当前 API 进程</button>
    </form>

    <div v-else class="unlocked-row">
      <p>凭据只在当前 API 进程内可解封；页面不会读取或回填任何已保存秘密。</p>
      <button type="button" class="btn secondary" :disabled="busy" @click="lock">
        立即锁定
      </button>
    </div>

    <p v-if="message" class="feedback" :class="{ error: messageIsError }" aria-live="polite">
      {{ message }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { ApiError } from "@/api/client";
import {
  initializeVault,
  lockVault,
  unlockVault,
  type VaultView,
} from "@/api/settings";
import StatusBadge from "@/components/StatusBadge.vue";

const props = defineProps<{ vault: VaultView }>();
const emit = defineEmits<{ changed: [] }>();

const passphrase = ref("");
const confirmation = ref("");
const busy = ref(false);
const message = ref("");
const messageIsError = ref(false);

const badge = computed<{
  variant: "warning" | "success" | "neutral";
  label: string;
}>(() => {
  if (props.vault.state === "UNINITIALIZED") {
    return { variant: "warning", label: "未初始化" };
  }
  if (props.vault.state === "UNLOCKED") {
    return { variant: "success", label: "当前进程已解锁" };
  }
  return { variant: "neutral", label: "已锁定" };
});

function clearSecrets(): void {
  passphrase.value = "";
  confirmation.value = "";
}

function safeMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "口令不正确，凭据库仍保持锁定。";
    if (err.status === 409) return "凭据库状态已变化，请刷新后重试。";
    if (err.status === 429) return "口令操作正在进行，请稍后重试。";
    if (err.isOffline) return "无法连接本地 API。";
  }
  return "凭据库操作失败；未保存任何口令或秘密。";
}

async function initialize(): Promise<void> {
  message.value = "";
  if (passphrase.value !== confirmation.value) {
    message.value = "两次口令不一致。";
    messageIsError.value = true;
    clearSecrets();
    return;
  }
  busy.value = true;
  try {
    await initializeVault(passphrase.value);
    message.value = "凭据库已初始化并解锁。";
    messageIsError.value = false;
    emit("changed");
  } catch (err) {
    message.value = safeMessage(err);
    messageIsError.value = true;
  } finally {
    clearSecrets();
    busy.value = false;
  }
}

async function unlock(): Promise<void> {
  busy.value = true;
  message.value = "";
  try {
    await unlockVault(passphrase.value);
    message.value = "当前 API 进程已解锁。";
    messageIsError.value = false;
    emit("changed");
  } catch (err) {
    message.value = safeMessage(err);
    messageIsError.value = true;
  } finally {
    clearSecrets();
    busy.value = false;
  }
}

async function lock(): Promise<void> {
  busy.value = true;
  message.value = "";
  clearSecrets();
  try {
    await lockVault();
    message.value = "凭据库已锁定。";
    messageIsError.value = false;
    emit("changed");
  } catch (err) {
    message.value = safeMessage(err);
    messageIsError.value = true;
  } finally {
    busy.value = false;
  }
}

onBeforeUnmount(clearSecrets);
</script>

<style scoped>
.vault-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-card);
}

.panel-header,
.unlocked-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

h2 {
  font-size: var(--font-size-xl);
}

p,
label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.panel-header p {
  margin-top: 4px;
}

.vault-form {
  display: grid;
  grid-template-columns: minmax(140px, 220px) minmax(220px, 1fr) auto;
  align-items: center;
  gap: 10px 12px;
}

.vault-form label:nth-of-type(2) {
  grid-column: 1;
}

input {
  height: 34px;
  min-width: 0;
  padding: 0 10px;
  color: var(--color-text-primary);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
}

.btn {
  min-height: 34px;
  padding: 0 14px;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
  font-weight: 600;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary {
  background: var(--color-accent-primary);
}

.secondary {
  border: 1px solid var(--color-border-strong);
  background: var(--color-bg-elevated);
}

.feedback {
  padding: 8px 10px;
  border-radius: var(--radius-md);
  color: var(--color-status-success);
  background: color-mix(in srgb, var(--color-status-success) 10%, transparent);
}

.feedback.error {
  color: var(--color-status-error);
  background: color-mix(in srgb, var(--color-status-error) 10%, transparent);
}

@media (max-width: 900px) {
  .panel-header,
  .unlocked-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .vault-form {
    grid-template-columns: 1fr;
  }

  .vault-form label:nth-of-type(2) {
    grid-column: auto;
  }
}
</style>
