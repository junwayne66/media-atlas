<script setup lang="ts">
import { invoke } from "@tauri-apps/api/core";
import { onMounted, ref } from "vue";

interface SidecarStatus {
  running: boolean;
  pid: number | null;
}

const sidecar = ref<SidecarStatus>({ running: false, pid: null });
const credentialHandle = ref("douyin-main-cookie");
const credentialSecret = ref("");
const credentialStored = ref<boolean | null>(null);
const message = ref("");

async function refresh() {
  sidecar.value = await invoke<SidecarStatus>("sidecar_status");
  if (credentialHandle.value) {
    credentialStored.value = await invoke<boolean>("credential_exists", {
      handle: credentialHandle.value,
    });
  }
}

async function startSidecar() {
  message.value = await invoke<string>("start_sidecar");
  await refresh();
}

async function stopSidecar() {
  message.value = await invoke<string>("stop_sidecar");
  await refresh();
}

async function storeCredential() {
  // 秘密值只进 Keychain，不落日志、不回显；此表单仅试点用
  await invoke("credential_store", {
    handle: credentialHandle.value,
    secret: credentialSecret.value,
  });
  credentialSecret.value = "";
  message.value = `已写入 Keychain：${credentialHandle.value}`;
  await refresh();
}

async function deleteCredential() {
  await invoke("credential_delete", { handle: credentialHandle.value });
  message.value = `已删除：${credentialHandle.value}`;
  await refresh();
}

onMounted(refresh);
</script>

<template>
  <main class="page">
    <h1>VideoForge Desktop</h1>
    <p class="subtitle">边缘 Worker 壳（P0 骨架）</p>

    <section class="card">
      <h2>Edge Agent Sidecar</h2>
      <p>
        状态：
        <strong :class="sidecar.running ? 'ok' : 'down'">
          {{ sidecar.running ? `运行中 (pid ${sidecar.pid})` : "未运行" }}
        </strong>
      </p>
      <p class="hint">Sidecar 是独立进程组：关闭本窗口后它会继续运行。</p>
      <button @click="startSidecar">启动</button>
      <button @click="stopSidecar">停止</button>
      <button @click="refresh">刷新</button>
    </section>

    <section class="card">
      <h2>Keychain 凭据 Broker</h2>
      <label>
        句柄
        <input v-model="credentialHandle" placeholder="credential handle" />
      </label>
      <label>
        秘密值
        <input v-model="credentialSecret" type="password" placeholder="仅写入 Keychain" />
      </label>
      <p v-if="credentialStored !== null">
        Keychain 中{{ credentialStored ? "已存在" : "不存在" }}该句柄
      </p>
      <button :disabled="!credentialSecret" @click="storeCredential">写入</button>
      <button @click="deleteCredential">删除</button>
    </section>

    <p v-if="message" class="hint">{{ message }}</p>
  </main>
</template>

<style scoped>
.page {
  max-width: 640px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

.subtitle,
.hint {
  color: #666;
  font-size: 0.9rem;
}

.card {
  margin-top: 1.5rem;
  padding: 1rem 1.5rem;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
}

.card label {
  display: block;
  margin: 0.5rem 0;
}

.card input {
  width: 100%;
  padding: 0.4rem;
  margin-top: 0.2rem;
  box-sizing: border-box;
}

.card button {
  margin: 0.5rem 0.5rem 0 0;
}

.ok {
  color: #0a7d33;
}

.down {
  color: #b3261e;
}
</style>
