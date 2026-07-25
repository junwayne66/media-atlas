<template>
  <AppLayout>
    <div class="script-editor-view">
      <div class="editor-content">
        <!-- Brief Panel -->
        <div class="brief-panel">
          <h3 class="panel-title">创作简报</h3>
          <select v-model="selectedProjectId" class="project-select">
            <option value="">选择项目…</option>
            <option v-for="p in projects.data.value ?? []" :key="p.id" :value="p.id">{{ p.title }}</option>
          </select>

          <StateBlock v-if="!selectedProjectId" kind="empty" title="请先选择一个项目。" />
          <StateBlock v-else-if="brief.loading.value" kind="loading" title="正在拉取 Brief…" />
          <StateBlock
            v-else-if="brief.notFound.value"
            kind="empty"
            title="该项目尚未生成 Brief（先跑分析 → 生成 Brief → 再生成脚本）。"
          />
          <StateBlock v-else-if="brief.error.value" kind="error" title="Brief 拉取失败" :detail="brief.error.value" />
          <template v-else-if="briefPayload">
            <div class="brief-section">
              <span class="brief-label">项目 ID</span>
              <span class="brief-value mono">{{ selectedProjectId }}</span>
            </div>
            <div class="brief-section">
              <span class="brief-label">目标平台</span>
              <span class="brief-value">{{ text(briefPayload.platform) }}</span>
            </div>
            <div class="brief-section">
              <span class="brief-label">视频时长</span>
              <span class="brief-value mono">~{{ Math.round(briefPayload.duration_target_ms / 1000) }}s</span>
            </div>
            <div class="brief-section">
              <span class="brief-label">角度 / 模式</span>
              <span class="brief-value">{{ text(briefPayload.angle) }} · {{ briefPayload.creation_mode }}</span>
            </div>
            <div class="brief-section">
              <span class="brief-label">目标</span>
              <span class="brief-value">{{ text(briefPayload.objective) }}</span>
            </div>
            <div class="brief-section">
              <span class="brief-label">受众画像</span>
              <span class="brief-value">{{ text(briefPayload.audience) }}</span>
            </div>
            <div class="brief-section">
              <span class="brief-label">Hook</span>
              <span class="brief-value">{{ briefPayload.hook ? briefPayload.hook.promise : "—" }}</span>
            </div>
            <div class="brief-section">
              <span class="brief-label">必须覆盖 Claim</span>
              <span class="brief-value mono">{{ (briefPayload.must_cover_claim_ids ?? []).join(", ") || "—" }}</span>
            </div>
          </template>
        </div>

        <!-- Script Panel -->
        <div class="script-panel">
          <div class="script-header">
            <div class="version-info">
              <h3 class="panel-title">脚本编辑</h3>
              <select v-if="scriptDocs.length" v-model.number="activeDocVersion" class="project-select">
                <option v-for="d in scriptDocs" :key="d.doc_version" :value="d.doc_version">v{{ d.doc_version }}</option>
              </select>
              <StatusBadge v-if="activeDoc" :variant="statusVariant" :label="activeDoc.status ?? '—'" />
            </div>
            <div class="script-actions">
              <button class="btn btn-secondary" :disabled="!selectedProjectId || generating" @click="reload">刷新</button>
              <button class="btn btn-primary" :disabled="!selectedProjectId || generating" @click="generate">
                {{ generating ? "生成中…" : "生成脚本" }}
              </button>
            </div>
          </div>

          <div class="script-body">
            <p v-if="genError" class="gen-error">{{ genError }}</p>

            <div v-if="activeDoc && activeDoc.issues.length" class="issue-box">
              <h4 class="issue-title">validate_script issues（{{ activeDoc.issues.length }}）</h4>
              <p v-for="(iss, i) in activeDoc.issues" :key="i" class="issue-line">{{ iss }}</p>
            </div>

            <StateBlock v-if="!selectedProjectId" kind="empty" title="请先选择一个项目。" />
            <StateBlock v-else-if="scripts.loading.value" kind="loading" title="正在拉取脚本版本…" />
            <StateBlock v-else-if="scripts.error.value" kind="error" title="脚本列表拉取失败" :detail="scripts.error.value" />
            <StateBlock
              v-else-if="scriptDocs.length === 0"
              kind="empty"
              title="该项目还没有脚本版本。点右上「生成脚本」（Fake 结构改写引擎）。"
            />
            <StateBlock
              v-else-if="sentences.length === 0"
              kind="empty"
              :title="`脚本 v${activeDocVersion} 没有句子。`"
            />

            <div v-for="(seg, i) in sentences" :key="seg.id" class="script-segment">
              <div class="seg-header">
                <span class="seg-num mono">{{ String(i + 1).padStart(2, "0") }}</span>
                <span class="seg-timecode mono">{{ seg.role }}</span>
                <StatusBadge
                  :variant="(seg.claim_ids ?? []).length ? 'info' : 'neutral'"
                  :label="
                    (seg.claim_ids ?? []).length
                      ? `引用 ${(seg.claim_ids ?? []).length} 条 Claim`
                      : '无 Claim 引用'
                  "
                />
              </div>
              <div class="seg-text">{{ seg.text }}</div>
              <div class="seg-meta">
                <span class="seg-meta-item mono">目标时长: {{ (seg.target_duration_ms / 1000).toFixed(1) }}s</span>
                <span class="seg-meta-item mono">语言: {{ seg.language }}</span>
                <span class="seg-meta-item mono">claim: {{ (seg.claim_ids ?? []).join(", ") || "—" }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import AppLayout from "@/components/AppLayout.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import StateBlock from "@/components/StateBlock.vue";
import { useAsync } from "@/composables/useAsync";
import { useSelectedProject } from "@/composables/useSelectedProject";
import { ApiError, errorText, formatDetail } from "@/api/client";
import { listProjects, type Project } from "@/api/projects";
import {
  DOC_VERSION_CONFLICT_MARK,
  generateScript,
  getBrief,
  listScripts,
  type CreativeBrief,
  type DocumentView,
  type ScriptSentence,
} from "@/api/creation";
import { text } from "@/utils/format";

type Variant = "success" | "warning" | "error" | "info" | "neutral";

const { selectedProjectId } = useSelectedProject();

const projects = useAsync<Project[]>();
const scripts = useAsync<DocumentView[]>();
const brief = useAsync<DocumentView>();

const activeDocVersion = ref<number>(0);
const generating = ref(false);
const genError = ref<string | null>(null);

const scriptDocs = computed(() => scripts.data.value ?? []);

const activeDoc = computed<DocumentView | null>(
  () => scriptDocs.value.find((d) => d.doc_version === activeDocVersion.value) ?? scriptDocs.value[0] ?? null,
);

const statusVariant = computed<Variant>(() => {
  const s = activeDoc.value?.status;
  if (!s) return "neutral";
  if (s === "OK") return "success";
  // needs_review / has issues → 橙
  return "warning";
});

const sentences = computed<ScriptSentence[]>(() => {
  const payload = activeDoc.value?.payload as { sentences?: ScriptSentence[] } | undefined;
  return payload?.sentences ?? [];
});

const briefPayload = computed<CreativeBrief | null>(() => (brief.data.value?.payload as CreativeBrief | undefined) ?? null);

async function reload(): Promise<void> {
  const id = selectedProjectId.value;
  if (!id) {
    scripts.reset();
    brief.reset();
    return;
  }
  await Promise.all([scripts.run(() => listScripts(id)), brief.run(() => getBrief(id))]);
  const docs = scripts.data.value ?? [];
  if (docs.length > 0 && !docs.some((d) => d.doc_version === activeDocVersion.value)) {
    activeDocVersion.value = docs[0]!.doc_version;
  }
}

async function generate(): Promise<void> {
  const id = selectedProjectId.value;
  if (!id) return;
  generating.value = true;
  genError.value = null;
  try {
    await generateScript(id);
  } catch (err) {
    // §11 实现细节 ①：只有"产物版本冲突"才自动重试一次；缺前置产物的 409 原样展示。
    const retriable =
      err instanceof ApiError &&
      err.isConflict &&
      (formatDetail(err.detail) ?? "").includes(DOC_VERSION_CONFLICT_MARK);
    if (retriable) {
      try {
        await generateScript(id);
      } catch (retryErr) {
        genError.value = `重试后仍失败：${errorText(retryErr)}`;
      }
    } else {
      genError.value = errorText(err);
    }
  } finally {
    generating.value = false;
    await reload();
  }
}

watch(selectedProjectId, () => void reload());

onMounted(async () => {
  const list = await projects.run(() => listProjects(50));
  if (!selectedProjectId.value && list && list.length > 0) {
    selectedProjectId.value = list[0]!.id;
  } else {
    await reload();
  }
});
</script>

<style scoped>
.script-editor-view {
  height: 100%;
  overflow: hidden;
}

.editor-content {
  display: flex;
  gap: 20px;
  padding: 24px;
  height: 100%;
  overflow: hidden;
}

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.project-select {
  height: 30px;
  padding: 0 8px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: var(--font-size-xs);
  font-family: inherit;
  cursor: pointer;
  max-width: 100%;
}

/* ===== Brief Panel ===== */
.brief-panel {
  width: 320px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  flex-shrink: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.brief-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.brief-section:last-child {
  border-bottom: none;
}

.brief-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.brief-value {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  line-height: 1.5;
  word-break: break-all;
}

/* ===== Script Panel ===== */
.script-panel {
  flex: 1;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.script-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.version-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.script-actions {
  display: flex;
  gap: 8px;
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

.btn-primary {
  background: var(--color-accent-primary);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-accent-primary-hover);
}

.btn-secondary {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-primary);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--color-bg-hover);
}

.script-body {
  flex: 1;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.gen-error {
  font-size: var(--font-size-base);
  color: var(--color-status-error);
  line-height: 1.6;
  padding: 10px 14px;
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-md);
  word-break: break-all;
}

.issue-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 16px;
  background: rgba(245, 166, 35, 0.08);
  border: 1px solid rgba(245, 166, 35, 0.3);
  border-radius: var(--radius-md);
}

.issue-title {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-status-warning);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.issue-line {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  line-height: 1.6;
  word-break: break-all;
}

.script-segment {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.seg-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.seg-num {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-text-tertiary);
}

.seg-timecode {
  font-size: var(--font-size-xs);
  color: var(--color-accent-primary);
}

.seg-text {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  line-height: 1.6;
}

.seg-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.seg-meta-item {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}
</style>
