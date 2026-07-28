<template>
  <section aria-labelledby="provider-settings-title">
    <div class="section-heading">
      <div>
        <h2 id="provider-settings-title">AI Provider 配置</h2>
        <p>配置只会保存到本地；本任务不会连接、测试或调用真实模型。</p>
      </div>
      <button type="button" class="btn secondary" @click="emit('reload')">重新载入</button>
    </div>

    <div class="provider-grid">
      <article v-for="kind in providerKinds" :key="kind" class="provider-card">
        <div class="card-heading">
          <div>
            <h3>{{ providerMeta[kind].title }}</h3>
            <p>{{ providerMeta[kind].description }}</p>
          </div>
          <StatusBadge
            :variant="readiness(kind).variant"
            :label="readiness(kind).label"
          />
        </div>

        <form class="form-grid" @submit.prevent="save(kind, 'KEEP')">
          <label :for="`${kind}-provider-name`">Provider 名称</label>
          <input
            :id="`${kind}-provider-name`"
            v-model="forms[kind].providerName"
            required
            maxlength="100"
            placeholder="例如 openai-compatible / local"
          />

          <label :for="`${kind}-model-name`">模型名称</label>
          <input
            :id="`${kind}-model-name`"
            v-model="forms[kind].modelName"
            maxlength="200"
            placeholder="可留空"
          />

          <label :for="`${kind}-base-url`">服务地址</label>
          <input
            :id="`${kind}-base-url`"
            v-model="forms[kind].baseUrl"
            maxlength="2048"
            inputmode="url"
            placeholder="https://…；本机可用 http://127.0.0.1"
          />

          <label :for="`${kind}-options`">非敏感选项（JSON）</label>
          <textarea
            :id="`${kind}-options`"
            v-model="forms[kind].optionsJson"
            rows="3"
            spellcheck="false"
            placeholder='例如 {"temperature":0.2}'
          ></textarea>

          <label class="check-row">
            <input v-model="forms[kind].enabled" type="checkbox" />
            启用本地配置
          </label>

          <div class="actions">
            <button type="submit" class="btn primary" :disabled="busy[kind]">
              保存非敏感配置
            </button>
            <button
              v-if="current(kind)"
              type="button"
              class="btn danger"
              :disabled="busy[kind]"
              @click="remove(kind)"
            >
              删除配置
            </button>
          </div>
        </form>

        <div class="credential-box">
          <div class="credential-title">
            <span>API Key / Provider 凭据</span>
            <StatusBadge
              :variant="current(kind)?.credential_configured ? 'success' : 'warning'"
              :label="current(kind)?.credential_configured ? '已加密保存' : '未配置'"
            />
          </div>
          <label :for="`${kind}-secret`">新凭据（不会回填旧值）</label>
          <input
            :id="`${kind}-secret`"
            v-model="secrets[kind]"
            type="password"
            autocomplete="off"
            spellcheck="false"
            maxlength="16384"
            :disabled="!vaultUnlocked || busy[kind]"
            placeholder="输入后选择替换"
          />
          <p v-if="!vaultUnlocked" class="hint">先解锁凭据库才能替换或清除秘密。</p>
          <div class="actions">
            <button
              type="button"
              class="btn secondary"
              :disabled="!vaultUnlocked || !secrets[kind] || busy[kind]"
              @click="save(kind, 'REPLACE')"
            >
              替换凭据
            </button>
            <button
              type="button"
              class="btn danger"
              :disabled="
                !vaultUnlocked ||
                !current(kind)?.credential_configured ||
                busy[kind]
              "
              @click="save(kind, 'CLEAR')"
            >
              清除凭据
            </button>
          </div>
        </div>

        <p
          v-if="messages[kind]"
          class="feedback"
          :class="{ error: messageErrors[kind] }"
          aria-live="polite"
        >
          {{ messages[kind] }}
        </p>
        <p v-if="current(kind)" class="version-line mono">
          version {{ current(kind)?.row_version }} · 更新于
          {{ new Date(current(kind)?.updated_at ?? "").toLocaleString() }}
        </p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, reactive, watch } from "vue";
import { ApiError } from "@/api/client";
import {
  removeProvider,
  saveProvider,
  type CredentialAction,
  type ProviderKind,
  type ProviderView,
} from "@/api/settings";
import StatusBadge from "@/components/StatusBadge.vue";

interface ProviderForm {
  providerName: string;
  modelName: string;
  baseUrl: string;
  enabled: boolean;
  optionsJson: string;
}

const props = defineProps<{
  providers: ProviderView[];
  vaultUnlocked: boolean;
}>();
const emit = defineEmits<{ reload: [] }>();

const providerKinds: ProviderKind[] = ["LLM", "ASR", "VLM"];
const providerMeta: Record<ProviderKind, { title: string; description: string }> = {
  LLM: { title: "LLM", description: "脚本、Blueprint 与文本推理配置" },
  ASR: { title: "ASR", description: "语音识别与词级时间戳配置" },
  VLM: { title: "VLM", description: "代表帧视觉理解配置" },
};

function emptyForm(): ProviderForm {
  return {
    providerName: "",
    modelName: "",
    baseUrl: "",
    enabled: false,
    optionsJson: "{}",
  };
}

const forms = reactive<Record<ProviderKind, ProviderForm>>({
  LLM: emptyForm(),
  ASR: emptyForm(),
  VLM: emptyForm(),
});
const secrets = reactive<Record<ProviderKind, string>>({ LLM: "", ASR: "", VLM: "" });
const busy = reactive<Record<ProviderKind, boolean>>({ LLM: false, ASR: false, VLM: false });
const messages = reactive<Record<ProviderKind, string>>({ LLM: "", ASR: "", VLM: "" });
const messageErrors = reactive<Record<ProviderKind, boolean>>({
  LLM: false,
  ASR: false,
  VLM: false,
});

function current(kind: ProviderKind): ProviderView | undefined {
  return props.providers.find((provider) => provider.kind === kind);
}

function syncFromServer(): void {
  for (const kind of providerKinds) {
    const provider = current(kind);
    forms[kind] = provider
      ? {
          providerName: provider.provider_name,
          modelName: provider.model_name ?? "",
          baseUrl: provider.base_url ?? "",
          enabled: provider.enabled,
          optionsJson: JSON.stringify(provider.options, null, 2),
        }
      : emptyForm();
    secrets[kind] = "";
  }
}

watch(() => props.providers, syncFromServer, { immediate: true, deep: true });

function readiness(kind: ProviderKind): {
  variant: "success" | "warning" | "neutral";
  label: string;
} {
  const provider = current(kind);
  if (!provider) return { variant: "neutral", label: "未保存" };
  if (provider.readiness === "MISSING_CREDENTIAL") {
    return { variant: "warning", label: "缺少凭据" };
  }
  if (provider.readiness === "CONFIGURED_UNVERIFIED") {
    return { variant: "success", label: "本地已配置" };
  }
  return { variant: "neutral", label: "已停用" };
}

function safeMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return "版本冲突：保留了当前输入，请重新载入后再保存。";
    if (err.status === 423) return "凭据库已锁定；本次秘密操作未写入。";
    if (err.status === 422) return "配置格式无效；请检查 URL、JSON 和敏感字段位置。";
    if (err.isOffline) return "无法连接本地 API。";
  }
  return "保存失败；凭据输入已从页面内存清除。";
}

async function save(kind: ProviderKind, action: CredentialAction): Promise<void> {
  let options: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(forms[kind].optionsJson || "{}");
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("options is not object");
    }
    options = parsed as Record<string, unknown>;
  } catch {
    messages[kind] = "非敏感选项必须是 JSON 对象。";
    messageErrors[kind] = true;
    secrets[kind] = "";
    return;
  }

  busy[kind] = true;
  messages[kind] = "";
  try {
    await saveProvider(kind, {
      provider_name: forms[kind].providerName,
      model_name: forms[kind].modelName || null,
      base_url: forms[kind].baseUrl || null,
      enabled: forms[kind].enabled,
      options,
      expected_version: current(kind)?.row_version ?? null,
      credential_action: action,
      ...(action === "REPLACE" ? { credential: { api_key: secrets[kind] } } : {}),
    });
    messages[kind] =
      action === "REPLACE"
        ? "配置与新凭据已保存。"
        : action === "CLEAR"
          ? "配置已保存，凭据已清除。"
          : "非敏感配置已保存；既有凭据保持不变。";
    messageErrors[kind] = false;
    emit("reload");
  } catch (err) {
    messages[kind] = safeMessage(err);
    messageErrors[kind] = true;
  } finally {
    secrets[kind] = "";
    busy[kind] = false;
  }
}

async function remove(kind: ProviderKind): Promise<void> {
  const provider = current(kind);
  if (!provider || !window.confirm(`删除 ${kind} 配置及其本地凭据？`)) return;
  busy[kind] = true;
  try {
    await removeProvider(kind, provider.row_version);
    messages[kind] = "配置已删除。";
    messageErrors[kind] = false;
    emit("reload");
  } catch (err) {
    messages[kind] = safeMessage(err);
    messageErrors[kind] = true;
  } finally {
    secrets[kind] = "";
    busy[kind] = false;
  }
}

onBeforeUnmount(() => {
  for (const kind of providerKinds) secrets[kind] = "";
});
</script>

<style scoped>
section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-heading,
.card-heading,
.credential-title,
.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

h2 {
  font-size: var(--font-size-xl);
}

h3 {
  font-size: var(--font-size-lg);
}

p,
label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr));
  gap: 14px;
}

.provider-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-card);
}

.form-grid,
.credential-box {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.credential-box {
  padding: 14px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
}

input:not([type="checkbox"]),
textarea {
  width: 100%;
  min-width: 0;
  padding: 8px 10px;
  color: var(--color-text-primary);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  resize: vertical;
}

.credential-box input {
  background: var(--color-bg-card);
}

.check-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.actions {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 4px;
}

.btn {
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: var(--font-size-xs);
  font-weight: 600;
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.primary {
  background: var(--color-accent-primary);
}

.secondary {
  border: 1px solid var(--color-border-strong);
  background: var(--color-bg-elevated);
}

.danger {
  color: var(--color-status-error);
  border: 1px solid color-mix(in srgb, var(--color-status-error) 35%, transparent);
  background: color-mix(in srgb, var(--color-status-error) 9%, transparent);
}

.hint,
.version-line {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.feedback {
  padding: 8px 10px;
  color: var(--color-status-success);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-status-success) 9%, transparent);
}

.feedback.error {
  color: var(--color-status-error);
  background: color-mix(in srgb, var(--color-status-error) 9%, transparent);
}

@media (max-width: 900px) {
  .section-heading,
  .card-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
