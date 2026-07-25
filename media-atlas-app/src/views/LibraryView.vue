<template>
  <AppLayout>
    <div class="library-view">
      <!-- Import Card -->
      <div class="import-card">
        <div class="import-header">
          <h2 class="section-title">采集入口</h2>
          <span class="import-status">
            <StatusBadge variant="warning" label="live 下载未配置" />
          </span>
        </div>
        <p class="import-hint">
          live 下载/短链展开未接通（stop-condition）：链接可解析、可入库，但成片需人工下载后用下方"本地文件导入"关联。
        </p>
        <div class="import-row">
          <div class="import-input">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="6" cy="6" r="4.25" stroke="currentColor" stroke-width="1.5" />
              <path d="M9.2 9.2L12 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
            <input
              v-model="urlInput"
              class="import-field"
              type="text"
              placeholder="粘贴视频 URL 或分享文本…"
              @keyup.enter="doResolve"
            />
          </div>
          <button class="btn btn-secondary" :disabled="busy || !urlInput" @click="doResolve">解析预览</button>
          <button class="btn btn-primary" :disabled="busy || !urlInput" @click="doImportUrl">导入</button>
        </div>

        <div class="import-row">
          <div class="import-input">
            <input
              v-model="pathInput"
              class="import-field"
              type="text"
              placeholder="本地文件绝对路径（macOS 试点）…"
              @keyup.enter="doImportFile"
            />
          </div>
          <button class="btn btn-secondary" :disabled="busy || !pathInput" @click="doImportFile">
            本地文件导入
          </button>
        </div>

        <div v-if="notice" class="notice" :class="`notice--${notice.kind}`">
          <span>{{ notice.text }}</span>
          <button class="notice-close" @click="notice = null">×</button>
        </div>

        <div v-if="resolved" class="resolve-preview">
          <div class="resolve-row">
            <span class="resolve-label">可解析</span>
            <StatusBadge
              :variant="resolved.resolvable ? 'success' : 'warning'"
              :label="resolved.resolvable ? '是' : '否'"
            />
          </div>
          <div class="resolve-row"><span class="resolve-label">平台</span><span class="mono">{{ text(resolved.platform) }}</span></div>
          <div class="resolve-row"><span class="resolve-label">content_id</span><span class="mono">{{ text(resolved.content_id) }}</span></div>
          <div class="resolve-row"><span class="resolve-label">canonical_url</span><span class="mono break">{{ text(resolved.canonical_url) }}</span></div>
          <div class="resolve-row"><span class="resolve-label">需展开短链</span><span class="mono">{{ resolved.needs_expansion ? "是" : "否" }}</span></div>
          <div class="resolve-row"><span class="resolve-label">原因</span><span>{{ text(resolved.reason) }}</span></div>
          <div class="resolve-row"><span class="resolve-label">error_code</span><span class="mono">{{ text(resolved.error_code) }}</span></div>
        </div>
      </div>

      <!-- Asset Table -->
      <div class="asset-table">
        <StateBlock v-if="sources.loading.value && !sources.loaded.value" kind="loading" title="正在拉取素材列表…" />
        <StateBlock
          v-else-if="sources.error.value"
          kind="error"
          :title="sources.offline.value ? '无法连接控制面 API，素材库无法加载' : '素材列表拉取失败'"
          :detail="sources.error.value"
        />
        <StateBlock
          v-else-if="assetRows.length === 0"
          kind="empty"
          title="素材库为空：已成功拉取，后端尚无 SourceAsset 记录。用上方入口导入第一条素材。"
        />
        <DataTable v-else :columns="columns" :rows="assetRows" hoverable>
          <template #cell-id="{ row }">
            <span class="asset-id mono" :title="row.id">{{ row.shortId }}</span>
          </template>
          <template #cell-title="{ row }">
            <div class="asset-title-cell">
              <span class="asset-title">{{ row.title }}</span>
              <span class="asset-source">{{ row.source }}</span>
            </div>
          </template>
          <template #cell-sha="{ row }">
            <span class="mono dim" :title="row.shaFull">{{ row.sha }}</span>
          </template>
          <template #cell-collectedAt="{ value }">
            <span class="mono dim">{{ value }}</span>
          </template>
          <template #cell-status="{ row }">
            <span :title="row.hint">
              <StatusBadge :variant="row.status.variant" :label="row.status.label" />
            </span>
          </template>
        </DataTable>
      </div>

      <!-- Duplicate Groups -->
      <div class="dup-card">
        <div class="dup-header">
          <h2 class="section-title">重复素材分组</h2>
          <span class="dup-count mono">{{ dupGroups.data.value?.length ?? 0 }} 组</span>
        </div>
        <p class="dup-hint">只展示分组证据；系统不提供删除源记录的操作（合同红线）。</p>
        <StateBlock v-if="dupGroups.error.value" kind="error" title="重复组拉取失败" :detail="dupGroups.error.value" />
        <StateBlock
          v-else-if="(dupGroups.data.value?.length ?? 0) === 0"
          kind="empty"
          title="未发现重复组：已成功拉取，当前素材没有构成重复分组。"
        />
        <div v-else class="dup-row">
          <div v-for="g in dupGroups.data.value ?? []" :key="g.group_id" class="dup-group">
            <div class="dup-group-header">
              <span class="dup-hash mono" :title="g.group_id">组 {{ shortId(g.group_id) }} · {{ g.layers.join("/") }}</span>
              <StatusBadge variant="warning" :label="`相似度 ${g.similarity.toFixed(2)}`" />
            </div>
            <div class="dup-items">
              <div v-for="m in g.member_asset_ids" :key="m" class="dup-item">
                <span class="dup-item-id mono" :title="m">{{ shortId(m) }}</span>
                <span class="dup-item-title">{{ assetTitle(m) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import AppLayout from "@/components/AppLayout.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import DataTable from "@/components/DataTable.vue";
import StateBlock from "@/components/StateBlock.vue";
import { useAsync } from "@/composables/useAsync";
import { errorText } from "@/api/client";
import {
  DISPOSITION_HINT,
  DISPOSITION_LABEL,
  importFile,
  importUrl,
  listDuplicateGroups,
  listSources,
  resolveSource,
  type DuplicateGroupView,
  type ResolveResponse,
  type SourceAsset,
  type SourceDisposition,
} from "@/api/sources";
import { datetime, shortId, text } from "@/utils/format";

const sources = useAsync<SourceAsset[]>();
const dupGroups = useAsync<DuplicateGroupView[]>();

const urlInput = ref("");
const pathInput = ref("");
const busy = ref(false);
const resolved = ref<ResolveResponse | null>(null);
const notice = ref<{ kind: "ok" | "warn" | "error"; text: string } | null>(null);

type Variant = "success" | "warning" | "error" | "info" | "neutral";
const DISPOSITION_VARIANT: Record<SourceDisposition, Variant> = {
  IMPORTED: "success",
  // MANUAL_FALLBACK 是既定流程而非报错 → info，不用 error 色
  MANUAL_FALLBACK: "info",
  NEEDS_EXPANSION: "warning",
  UNRESOLVABLE: "error",
};

const columns = [
  { key: "id", label: "ID", width: "110px" },
  { key: "title", label: "输入 / 来源", flex: "2" },
  { key: "sha", label: "文件 SHA256", width: "130px" },
  { key: "collectedAt", label: "导入时间", width: "150px" },
  { key: "status", label: "处置", width: "130px" },
];

const assetRows = computed(() =>
  (sources.data.value ?? []).map((a) => ({
    id: a.id,
    shortId: shortId(a.id),
    title: a.canonical_url ?? a.local_path ?? a.original_input,
    source: `${a.platform || "unknown"} · ${a.reason}`,
    sha: a.file_sha256 ? `${a.file_sha256.slice(0, 12)}…` : "—",
    shaFull: a.file_sha256 ?? "未计算（无本地文件）",
    collectedAt: datetime(a.created_at),
    status: { variant: DISPOSITION_VARIANT[a.disposition], label: DISPOSITION_LABEL[a.disposition] },
    hint: DISPOSITION_HINT[a.disposition],
  })),
);

function assetTitle(assetId: string): string {
  const found = (sources.data.value ?? []).find((a) => a.id === assetId);
  return found ? (found.canonical_url ?? found.original_input) : assetId;
}

async function reload(): Promise<void> {
  await Promise.all([
    sources.run(() => listSources({ limit: 50 })),
    dupGroups.run(() => listDuplicateGroups()),
  ]);
}

async function doResolve(): Promise<void> {
  busy.value = true;
  notice.value = null;
  try {
    resolved.value = await resolveSource(urlInput.value.trim());
  } catch (err) {
    resolved.value = null;
    notice.value = { kind: "error", text: `解析失败：${errorText(err)}` };
  } finally {
    busy.value = false;
  }
}

async function doImportUrl(): Promise<void> {
  busy.value = true;
  notice.value = null;
  try {
    const asset = await importUrl(urlInput.value.trim());
    notice.value = {
      kind: asset.disposition === "UNRESOLVABLE" ? "warn" : "ok",
      text: `已入库 ${asset.id}（处置：${DISPOSITION_LABEL[asset.disposition]}）— ${DISPOSITION_HINT[asset.disposition]}`,
    };
    await reload();
  } catch (err) {
    notice.value = { kind: "error", text: `导入失败：${errorText(err)}` };
  } finally {
    busy.value = false;
  }
}

async function doImportFile(): Promise<void> {
  busy.value = true;
  notice.value = null;
  try {
    const asset = await importFile(pathInput.value.trim());
    notice.value = { kind: "ok", text: `本地文件已入库 ${asset.id}（SHA256 ${asset.file_sha256 ?? "—"}）` };
    pathInput.value = "";
    await reload();
  } catch (err) {
    notice.value = { kind: "error", text: `本地文件导入失败：${errorText(err)}` };
  } finally {
    busy.value = false;
  }
}

onMounted(reload);
</script>

<style scoped>
.library-view {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
}

.section-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

/* ===== Import Card ===== */
.import-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.import-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.import-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

.import-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.import-input {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 12px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
}

.import-field {
  flex: 1;
  height: 100%;
  border: none;
  background: transparent;
  outline: none;
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
  font-family: inherit;
}

.import-field::placeholder {
  color: var(--color-text-tertiary);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 38px;
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

.btn-primary {
  background: var(--color-accent-primary);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-accent-primary-hover);
}

.btn-secondary {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-strong);
  color: var(--color-text-primary);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--color-bg-hover);
}

.notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-primary);
  line-height: 1.6;
}

.notice--warn {
  border-color: rgba(245, 166, 35, 0.4);
  color: var(--color-status-warning);
}

.notice--error {
  border-color: rgba(239, 68, 68, 0.4);
  color: var(--color-status-error);
}

.notice-close {
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: var(--font-size-xl);
  line-height: 1;
}

.resolve-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
}

.resolve-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--font-size-xs);
  color: var(--color-text-primary);
}

.resolve-label {
  min-width: 110px;
  color: var(--color-text-tertiary);
}

.break {
  word-break: break-all;
}

/* ===== Asset Table ===== */
.asset-table {
  flex: 1;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.asset-id {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.asset-title-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.asset-title {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
}

.asset-source {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
}

.mono.dim {
  color: var(--color-text-tertiary);
}

/* ===== Duplicate Groups ===== */
.dup-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dup-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.dup-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.dup-count {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.dup-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.dup-group {
  flex: 1;
  min-width: 280px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.dup-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.dup-hash {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.dup-items {
  display: flex;
  flex-direction: column;
}

.dup-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.dup-item:last-child {
  border-bottom: none;
}

.dup-item-id {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  min-width: 90px;
}

.dup-item-title {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
