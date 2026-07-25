<template>
  <AppLayout>
    <div class="review-view">
      <div class="review-content">
        <!-- Queue Panel -->
        <div class="queue-panel">
          <div class="queue-header">
            <h3 class="panel-title">审核决定</h3>
            <span class="queue-count mono">{{ decisions.data.value?.length ?? 0 }} 条</span>
          </div>

          <div class="entity-form">
            <span class="form-label">实体 ID（后端按 entity_id 查询，必填）</span>
            <div class="entity-row">
              <input
                v-model="entityId"
                class="form-input mono"
                type="text"
                placeholder="项目 / 成片包 / 模板 的 id"
                @keyup.enter="reload"
              />
              <button class="btn btn-secondary" :disabled="!entityId || decisions.loading.value" @click="reload">
                查询
              </button>
            </div>
            <div v-if="(projects.data.value?.length ?? 0) > 0" class="entity-row">
              <select class="form-input" @change="pickProject">
                <option value="">从项目列表填入…</option>
                <option v-for="p in projects.data.value ?? []" :key="p.id" :value="p.id">{{ p.title }}</option>
              </select>
            </div>
          </div>

          <div class="queue-list">
            <StateBlock v-if="!entityId" kind="empty" title="请输入或选择一个实体 ID 后查询。" />
            <StateBlock v-else-if="decisions.loading.value" kind="loading" title="正在拉取审核决定…" />
            <StateBlock
              v-else-if="decisions.error.value"
              kind="error"
              :title="decisions.offline.value ? '无法连接控制面 API' : '审核决定拉取失败'"
              :detail="decisions.error.value"
            />
            <StateBlock
              v-else-if="(decisions.data.value?.length ?? 0) === 0"
              kind="empty"
              title="该实体没有审核决定：已成功拉取，后端无记录。"
            />
            <div
              v-for="d in decisions.data.value ?? []"
              :key="d.id"
              class="queue-item"
              :class="{ active: d.id === selectedId }"
              @click="select(d.id)"
            >
              <div class="queue-item-top">
                <span class="queue-id mono" :title="d.id">{{ shortId(d.id, 10) }}</span>
                <StatusBadge :variant="decisionVariant(d.decision)" :label="DECISION_LABEL[d.decision]" />
              </div>
              <div class="queue-item-title">{{ SCOPE_LABEL[d.scope] }} · v{{ d.entity_version }}</div>
              <div class="queue-item-meta">
                <span class="mono">{{ datetime(d.created_at) }}</span>
                <span>·</span>
                <span>{{ d.reviewer_id }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Detail Panel -->
        <div class="detail-panel">
          <div class="detail-header">
            <div>
              <h3 class="panel-title">审核详情</h3>
              <span class="detail-id mono">{{ selected ? selected.id : "—" }}</span>
            </div>
            <StatusBadge
              v-if="selected"
              :variant="decisionVariant(selected.decision)"
              :label="DECISION_LABEL[selected.decision]"
            />
          </div>

          <div class="detail-body">
            <StateBlock v-if="!selected" kind="empty" title="左侧选择一条审核决定查看详情。" />
            <template v-else>
              <div class="detail-section">
                <h4 class="detail-label">决定信息</h4>
                <div class="info-grid">
                  <div class="info-item">
                    <span class="info-label">实体</span>
                    <span class="info-value mono break">{{ selected.entity_id }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">实体版本</span>
                    <span class="info-value mono">v{{ selected.entity_version }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">内容摘要</span>
                    <span class="info-value mono break">{{ selected.content_digest }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">签名</span>
                    <span class="info-value mono break">{{ selected.signature }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">策略快照</span>
                    <span class="info-value mono break">{{ selected.policy_snapshot_id }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">QC 报告</span>
                    <span class="info-value mono break">{{ (selected.qc_report_ids ?? []).join(", ") || "—" }}</span>
                  </div>
                </div>
                <p v-if="selected.note" class="note-text">{{ selected.note }}</p>
              </div>

              <div class="detail-section">
                <h4 class="detail-label">审批有效性校验（修改失效红线）</h4>
                <p class="hint">
                  实体版本或内容摘要变化后，旧审批立即失效，必须重新审批——把当前实体的版本/摘要填进来即可验证。
                </p>
                <div class="validate-form">
                  <label class="v-row">
                    <span class="v-label">当前版本</span>
                    <input v-model.number="vForm.version" class="form-input mono" type="number" min="1" />
                  </label>
                  <label class="v-row">
                    <span class="v-label">当前内容摘要</span>
                    <input v-model="vForm.digest" class="form-input mono" type="text" />
                  </label>
                  <label class="v-row">
                    <span class="v-label">当前实体 ID</span>
                    <input v-model="vForm.entityId" class="form-input mono" type="text" />
                  </label>
                </div>
              </div>

              <div v-if="validateResult" class="detail-section">
                <h4 class="detail-label">校验结果</h4>
                <div class="checklist">
                  <div class="check-item">
                    <span class="check-icon" :class="validateResult.valid ? 'check-pass' : 'check-warn'">
                      <svg v-if="validateResult.valid" width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M2 6L5 9L10 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                      <svg v-else width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M6 2V7M6 9.5V10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                      </svg>
                    </span>
                    <span class="check-label">{{ validateResult.valid ? "审批有效" : "审批已失效——需重新审批" }}</span>
                  </div>
                  <div v-for="(iss, i) in validateResult.issues" :key="i" class="check-item">
                    <span class="check-icon check-warn">
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M6 2V7M6 9.5V10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                      </svg>
                    </span>
                    <span class="check-label mono">{{ iss }}</span>
                  </div>
                </div>
              </div>
              <p v-if="validateError" class="err-line">{{ validateError }}</p>
            </template>
          </div>

          <div v-if="selected" class="detail-footer">
            <span class="footer-note">FATAL / BLOCKER 级问题没有"强制通过"入口（合同红线）。</span>
            <button class="btn btn-primary" :disabled="validating" @click="doValidate">
              {{ validating ? "校验中…" : "校验审批有效性" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import AppLayout from "@/components/AppLayout.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import StateBlock from "@/components/StateBlock.vue";
import { useAsync } from "@/composables/useAsync";
import { errorText } from "@/api/client";
import {
  DECISION_LABEL,
  listReviewDecisions,
  SCOPE_LABEL,
  validateReviewDecision,
  type ApprovalValidateResponse,
  type ReviewDecision,
  type ReviewDecisionKind,
} from "@/api/review";
import { listProjects, type Project } from "@/api/projects";
import { datetime, shortId } from "@/utils/format";

type Variant = "success" | "warning" | "error" | "info" | "neutral";

const decisions = useAsync<ReviewDecision[]>();
const projects = useAsync<Project[]>();

const entityId = ref("");
const selectedId = ref("");
const validating = ref(false);
const validateError = ref<string | null>(null);
const validateResult = ref<ApprovalValidateResponse | null>(null);

const vForm = reactive({ version: 1, digest: "", entityId: "" });

const selected = computed<ReviewDecision | null>(
  () => (decisions.data.value ?? []).find((d) => d.id === selectedId.value) ?? null,
);

function decisionVariant(kind: ReviewDecisionKind): Variant {
  if (kind === "APPROVED") return "success";
  if (kind === "REJECTED") return "error";
  return "warning";
}

function select(id: string): void {
  selectedId.value = id;
  validateResult.value = null;
  validateError.value = null;
}

function pickProject(e: Event): void {
  const value = (e.target as HTMLSelectElement).value;
  if (value) {
    entityId.value = value;
    void reload();
  }
}

async function reload(): Promise<void> {
  if (!entityId.value) return;
  const list = await decisions.run(() => listReviewDecisions(entityId.value.trim()));
  selectedId.value = list && list.length > 0 ? list[0]!.id : "";
  validateResult.value = null;
}

watch(selected, (d) => {
  if (d) {
    // 预填当前决定自身的值：改任一项即可看到"修改即失效"
    vForm.version = d.entity_version;
    vForm.digest = d.content_digest;
    vForm.entityId = d.entity_id;
  }
});

async function doValidate(): Promise<void> {
  const d = selected.value;
  if (!d) return;
  validating.value = true;
  validateError.value = null;
  try {
    validateResult.value = await validateReviewDecision(d.id, {
      current_entity_version: vForm.version,
      current_content_digest: vForm.digest,
      current_entity_id: vForm.entityId || null,
    });
  } catch (err) {
    validateResult.value = null;
    validateError.value = errorText(err);
  } finally {
    validating.value = false;
  }
}

onMounted(async () => {
  await projects.run(() => listProjects(50));
});
</script>

<style scoped>
.review-view {
  height: 100%;
  overflow: hidden;
}

.review-content {
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

.hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

/* ===== Queue Panel ===== */
.queue-panel {
  width: 340px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}

.queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.queue-count {
  font-size: var(--font-size-sm);
  color: var(--color-accent-primary);
}

.entity-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.form-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.entity-row {
  display: flex;
  gap: 8px;
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

.queue-list {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-item {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  transition: all 150ms ease;
}

.queue-item:hover {
  border-color: var(--color-border-strong);
}

.queue-item.active {
  border-color: var(--color-accent-primary);
  background: rgba(59, 130, 246, 0.05);
}

.queue-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.queue-id {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.queue-item-title {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  font-weight: 500;
}

.queue-item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* ===== Detail Panel ===== */
.detail-panel {
  flex: 1;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 20px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.detail-id {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.detail-body {
  flex: 1;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  min-width: 0;
}

.info-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.info-value {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  font-weight: 500;
}

.break {
  word-break: break-all;
}

.note-text {
  font-size: var(--font-size-base);
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.validate-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.v-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.v-label {
  min-width: 110px;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.checklist {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.check-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
}

.check-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  flex-shrink: 0;
}

.check-pass {
  background: rgba(60, 207, 78, 0.15);
  color: var(--color-status-success);
}

.check-warn {
  background: rgba(245, 166, 35, 0.15);
  color: var(--color-status-warning);
}

.check-label {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  word-break: break-all;
}

.err-line {
  font-size: var(--font-size-xs);
  color: var(--color-status-error);
  line-height: 1.6;
  word-break: break-all;
}

.detail-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid var(--color-border-subtle);
}

.footer-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 34px;
  padding: 0 20px;
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
</style>
