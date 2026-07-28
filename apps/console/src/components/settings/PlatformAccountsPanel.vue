<template>
  <section aria-labelledby="account-settings-title">
    <div class="section-heading">
      <div>
        <h2 id="account-settings-title">平台账号绑定</h2>
        <p>
          这里只登记本地材料，所有账号始终“未在线验证”；不会发起 OAuth、登录、验证码或发布。
        </p>
      </div>
      <StatusBadge variant="warning" label="真实联网已禁用" />
    </div>

    <div v-if="accounts.length" class="account-grid">
      <article v-for="account in accounts" :key="account.id" class="account-card">
        <div class="card-heading">
          <div>
            <h3>{{ account.display_name }}</h3>
            <p class="mono">{{ account.platform }} · {{ account.external_account_id }}</p>
          </div>
          <StatusBadge variant="warning" label="UNVERIFIED" />
        </div>
        <dl>
          <div><dt>方式</dt><dd>{{ methodLabel(account.auth_method) }}</dd></div>
          <div><dt>保存位置</dt><dd>{{ bindingLabel(account.binding) }}</dd></div>
          <div>
            <dt>凭据</dt>
            <dd>{{ account.credential_configured ? "已登记" : "未配置" }}</dd>
          </div>
          <div><dt>状态</dt><dd>{{ account.enabled ? "已启用配置" : "已停用" }}</dd></div>
        </dl>
        <div class="actions">
          <button type="button" class="btn secondary" @click="edit(account)">编辑</button>
          <button
            type="button"
            class="btn danger"
            :disabled="busy"
            @click="remove(account)"
          >
            删除绑定
          </button>
        </div>
      </article>
    </div>
    <StateBlock
      v-else
      kind="empty"
      title="尚未登记平台账号。"
      detail="可保存真实账号的本地引用，但本任务不会进行在线验证。"
    />

    <form class="editor" @submit.prevent="submit">
      <div class="editor-heading">
        <div>
          <h3>{{ editingId ? "编辑账号绑定" : "新增账号绑定" }}</h3>
          <p v-if="editingId" class="mono">version {{ editingVersion }}</p>
        </div>
        <button v-if="editingId" type="button" class="btn secondary" @click="reset">
          取消编辑
        </button>
      </div>

      <div class="form-grid">
        <label for="account-platform">平台</label>
        <select id="account-platform" v-model="form.platform">
          <option value="DOUYIN">抖音</option>
          <option value="TIKTOK">TikTok</option>
        </select>

        <label for="account-display-name">显示名</label>
        <input
          id="account-display-name"
          v-model="form.displayName"
          required
          maxlength="200"
        />

        <label for="account-external-id">平台账号标识</label>
        <input
          id="account-external-id"
          v-model="form.externalAccountId"
          required
          maxlength="200"
          autocomplete="off"
        />

        <label for="account-auth-method">绑定方式</label>
        <select
          id="account-auth-method"
          v-model="form.authMethod"
          @change="onMethodChanged"
        >
          <option value="OFFICIAL_API">官方 API / OAuth Token</option>
          <option value="BROWSER_AUTOMATION">Desktop 浏览器会话</option>
          <option value="ANDROID_DEVICE">Android 设备会话</option>
          <option value="MANUAL_EXPORT">手工导出</option>
        </select>

        <label for="account-locale">Locale</label>
        <input id="account-locale" v-model="form.locale" required maxlength="20" />

        <label for="account-window">发布窗口（非敏感说明）</label>
        <input id="account-window" v-model="form.publishingWindow" maxlength="200" />

        <label class="check-row">
          <input v-model="form.enabled" type="checkbox" />
          启用本地账号配置
        </label>
      </div>

      <div class="credential-box">
        <div class="credential-title">
          <div>
            <h4>凭据处理</h4>
            <p>{{ bindingHelp }}</p>
          </div>
          <StatusBadge
            :variant="editingCredentialConfigured ? 'success' : 'neutral'"
            :label="editingCredentialConfigured ? '当前已登记' : '当前未配置'"
          />
        </div>

        <label for="account-credential-action">本次动作</label>
        <select
          id="account-credential-action"
          v-model="credentialAction"
          :disabled="form.authMethod === 'MANUAL_EXPORT'"
        >
          <option value="KEEP">保持原凭据</option>
          <option value="REPLACE">替换 / 登记</option>
          <option value="CLEAR">清除本地引用</option>
        </select>

        <template v-if="credentialAction === 'REPLACE' && form.authMethod === 'OFFICIAL_API'">
          <label for="account-access-token">Access Token</label>
          <input
            id="account-access-token"
            v-model="accessToken"
            type="password"
            autocomplete="off"
            spellcheck="false"
            maxlength="16384"
          />
          <label for="account-refresh-token">Refresh Token（可选）</label>
          <input
            id="account-refresh-token"
            v-model="refreshToken"
            type="password"
            autocomplete="off"
            spellcheck="false"
            maxlength="16384"
          />
          <label for="account-client-secret">Client Secret（可选）</label>
          <input
            id="account-client-secret"
            v-model="clientSecret"
            type="password"
            autocomplete="off"
            spellcheck="false"
            maxlength="16384"
          />
        </template>

        <template
          v-else-if="
            credentialAction === 'REPLACE' &&
            (form.authMethod === 'BROWSER_AUTOMATION' ||
              form.authMethod === 'ANDROID_DEVICE')
          "
        >
          <label for="account-external-handle">
            {{ form.authMethod === "BROWSER_AUTOMATION" ? "Keychain handle" : "Device handle" }}
          </label>
          <input
            id="account-external-handle"
            v-model="externalHandle"
            maxlength="200"
            autocomplete="off"
            spellcheck="false"
            placeholder="仅填不透明 handle，不要粘贴 Cookie/会话"
          />
        </template>
      </div>

      <p
        v-if="message"
        class="feedback"
        :class="{ error: messageIsError }"
        aria-live="polite"
      >
        {{ message }}
      </p>
      <div class="actions">
        <button type="submit" class="btn primary" :disabled="submitDisabled">
          {{ busy ? "保存中…" : editingId ? "保存修改" : "新增绑定" }}
        </button>
      </div>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from "vue";
import { ApiError } from "@/api/client";
import {
  createAccount,
  removeAccount,
  saveAccount,
  type AccountAuthMethod,
  type AccountBinding,
  type CredentialAction,
  type Platform,
  type PlatformAccountView,
} from "@/api/settings";
import StateBlock from "@/components/StateBlock.vue";
import StatusBadge from "@/components/StatusBadge.vue";

interface AccountForm {
  platform: Platform;
  displayName: string;
  externalAccountId: string;
  authMethod: AccountAuthMethod;
  locale: string;
  publishingWindow: string;
  enabled: boolean;
}

const props = defineProps<{
  accounts: PlatformAccountView[];
  vaultUnlocked: boolean;
}>();
const emit = defineEmits<{ reload: [] }>();

const form = reactive<AccountForm>({
  platform: "DOUYIN",
  displayName: "",
  externalAccountId: "",
  authMethod: "OFFICIAL_API",
  locale: "zh-CN",
  publishingWindow: "",
  enabled: false,
});
const editingId = ref<string | null>(null);
const editingVersion = ref<number | null>(null);
const editingCredentialConfigured = ref(false);
const credentialAction = ref<CredentialAction>("KEEP");
const accessToken = ref("");
const refreshToken = ref("");
const clientSecret = ref("");
const externalHandle = ref("");
const busy = ref(false);
const message = ref("");
const messageIsError = ref(false);

function bindingFor(method: AccountAuthMethod): AccountBinding {
  if (method === "BROWSER_AUTOMATION") return "DESKTOP";
  if (method === "ANDROID_DEVICE") return "DEVICE";
  return "SERVER_ENCRYPTED";
}

const bindingHelp = computed(() => {
  if (form.authMethod === "BROWSER_AUTOMATION") {
    return "Cookie 只能写入 macOS Keychain；这里仅登记 Desktop handle。";
  }
  if (form.authMethod === "ANDROID_DEVICE") {
    return "Android 会话留在设备端；这里仅登记 device handle。";
  }
  if (form.authMethod === "MANUAL_EXPORT") {
    return "手工导出不保存平台凭据。";
  }
  return "Token 将进入本地凭据库，以 AES-GCM 认证密文保存。";
});

const submitDisabled = computed(() => {
  if (busy.value) return true;
  const serverSecretMutation =
    form.authMethod === "OFFICIAL_API" && credentialAction.value !== "KEEP";
  return serverSecretMutation && !props.vaultUnlocked;
});

function clearSecrets(): void {
  accessToken.value = "";
  refreshToken.value = "";
  clientSecret.value = "";
  externalHandle.value = "";
}

function reset(): void {
  form.platform = "DOUYIN";
  form.displayName = "";
  form.externalAccountId = "";
  form.authMethod = "OFFICIAL_API";
  form.locale = "zh-CN";
  form.publishingWindow = "";
  form.enabled = false;
  editingId.value = null;
  editingVersion.value = null;
  editingCredentialConfigured.value = false;
  credentialAction.value = "KEEP";
  message.value = "";
  clearSecrets();
}

function edit(account: PlatformAccountView): void {
  form.platform = account.platform;
  form.displayName = account.display_name;
  form.externalAccountId = account.external_account_id;
  form.authMethod = account.auth_method;
  form.locale = account.locale;
  form.publishingWindow = account.publishing_window ?? "";
  form.enabled = account.enabled;
  editingId.value = account.id;
  editingVersion.value = account.row_version;
  editingCredentialConfigured.value = account.credential_configured;
  credentialAction.value = "KEEP";
  message.value = "";
  clearSecrets();
}

function onMethodChanged(): void {
  credentialAction.value = editingId.value ? "CLEAR" : "KEEP";
  clearSecrets();
}

function methodLabel(method: AccountAuthMethod): string {
  return {
    OFFICIAL_API: "官方 API",
    BROWSER_AUTOMATION: "Desktop 浏览器",
    ANDROID_DEVICE: "Android 设备",
    MANUAL_EXPORT: "手工导出",
  }[method];
}

function bindingLabel(binding: AccountBinding): string {
  return {
    SERVER_ENCRYPTED: "本地加密库",
    DESKTOP: "macOS Keychain",
    DEVICE: "设备端",
  }[binding];
}

function safeMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return "版本或账号标识冲突；请重新载入后再修改。";
    if (err.status === 423) return "凭据库已锁定；服务端凭据未被修改。";
    if (err.status === 422) return "绑定组合或字段格式无效；未保存任何秘密。";
    if (err.isOffline) return "无法连接本地 API。";
  }
  return "账号设置保存失败；本次凭据输入已清除。";
}

async function submit(): Promise<void> {
  busy.value = true;
  message.value = "";
  const action = form.authMethod === "MANUAL_EXPORT" ? "KEEP" : credentialAction.value;
  const binding = bindingFor(form.authMethod);
  const body = {
    platform: form.platform,
    display_name: form.displayName,
    external_account_id: form.externalAccountId,
    auth_method: form.authMethod,
    binding,
    locale: form.locale,
    publishing_window: form.publishingWindow || null,
    enabled: form.enabled,
    expected_version: editingVersion.value,
    credential_action: action,
    ...(action === "REPLACE" && binding === "SERVER_ENCRYPTED"
      ? {
          credential: {
            access_token: accessToken.value,
            ...(refreshToken.value ? { refresh_token: refreshToken.value } : {}),
            ...(clientSecret.value ? { client_secret: clientSecret.value } : {}),
          },
        }
      : {}),
    ...(action === "REPLACE" && binding !== "SERVER_ENCRYPTED"
      ? { external_credential_ref: externalHandle.value }
      : {}),
  };

  try {
    if (editingId.value) {
      await saveAccount(editingId.value, body);
    } else {
      await createAccount(body);
    }
    reset();
    message.value = "账号绑定已本地保存，仍未在线验证。";
    messageIsError.value = false;
    emit("reload");
  } catch (err) {
    message.value = safeMessage(err);
    messageIsError.value = true;
  } finally {
    clearSecrets();
    busy.value = false;
  }
}

async function remove(account: PlatformAccountView): Promise<void> {
  const externalNote =
    account.binding === "SERVER_ENCRYPTED"
      ? "关联服务端密文会一并删除。"
      : "本地引用会失效；请另在 Keychain/设备端清理实体会话。";
  if (!window.confirm(`删除 ${account.display_name}？${externalNote}`)) return;
  busy.value = true;
  try {
    await removeAccount(account.id, account.row_version);
    message.value = "账号绑定已删除。";
    messageIsError.value = false;
    if (editingId.value === account.id) reset();
    emit("reload");
  } catch (err) {
    message.value = safeMessage(err);
    messageIsError.value = true;
  } finally {
    clearSecrets();
    busy.value = false;
  }
}

onBeforeUnmount(clearSecrets);
</script>

<style scoped>
section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-heading,
.card-heading,
.editor-heading,
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

h4 {
  font-size: var(--font-size-base);
}

p,
label,
dt,
dd {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
}

.account-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
  gap: 12px;
}

.account-card,
.editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-card);
}

dl {
  display: flex;
  flex-direction: column;
}

dl div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.form-grid {
  display: grid;
  grid-template-columns: minmax(150px, 210px) minmax(220px, 1fr);
  align-items: center;
  gap: 10px 12px;
}

input:not([type="checkbox"]),
select {
  width: 100%;
  min-width: 0;
  height: 34px;
  padding: 0 10px;
  color: var(--color-text-primary);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
}

.check-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  grid-column: 2;
}

.credential-box {
  display: grid;
  grid-template-columns: minmax(150px, 210px) minmax(220px, 1fr);
  align-items: center;
  gap: 10px 12px;
  padding: 14px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
}

.credential-title {
  grid-column: 1 / -1;
}

.credential-box input,
.credential-box select {
  background: var(--color-bg-card);
}

.actions {
  justify-content: flex-start;
  flex-wrap: wrap;
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
  .card-heading,
  .credential-title {
    align-items: flex-start;
    flex-direction: column;
  }

  .form-grid,
  .credential-box {
    grid-template-columns: 1fr;
  }

  .check-row {
    grid-column: auto;
  }
}
</style>
