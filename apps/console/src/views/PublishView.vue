<template>
  <AppLayout>
    <div class="publish-view">
      <div class="publish-content">
        <!-- Job List Panel -->
        <div class="job-panel">
          <div class="job-header">
            <h3 class="panel-title">发布任务</h3>
            <button class="btn btn-primary btn-sm" @click="showCreate = !showCreate">
              {{ showCreate ? "收起" : "新建任务" }}
            </button>
          </div>

          <div v-if="showCreate" class="create-form">
            <label class="form-row">
              <span class="form-label">账号</span>
              <input v-model="form.account_id" class="form-input" type="text" />
            </label>
            <label class="form-row">
              <span class="form-label">平台</span>
              <select v-model="form.platform" class="form-input">
                <option value="TIKTOK">TIKTOK</option>
                <option value="DOUYIN">DOUYIN</option>
              </select>
            </label>
            <label class="form-row">
              <span class="form-label">成片摘要</span>
              <input v-model="form.media_digest" class="form-input mono" type="text" />
            </label>
            <label class="form-row">
              <span class="form-label">标题</span>
              <input v-model="form.title" class="form-input" type="text" />
            </label>
            <label class="form-row">
              <span class="form-label">语言</span>
              <input v-model="form.language" class="form-input" type="text" />
            </label>
            <label class="form-row">
              <span class="form-label">发布窗口</span>
              <input v-model="form.publishing_window" class="form-input mono" type="text" placeholder="immediate 或 22:00-02:00" />
            </label>
            <label class="form-row">
              <span class="form-label">副本序号</span>
              <input v-model.number="form.copy_index" class="form-input mono" type="number" min="0" />
            </label>
            <p class="form-hint">
              副本序号 0 = 同内容去重（返回既有任务）；≥1 才派生新幂等键（= 有意的第二条帖子）。
              元数据参与幂等键、建好后不可变——要改元数据请新建任务。
            </p>
            <button class="btn btn-primary btn-sm" :disabled="busy" @click="doCreate">提交新建</button>
          </div>

          <div class="calendar-box">
            <div class="calendar-head">
              <span class="calendar-title">发布日历预览</span>
              <button class="link-btn" @click="loadCalendar">查询</button>
            </div>
            <input v-model="calendarWindow" class="form-input mono" type="text" placeholder="immediate 或 22:00-02:00" />
            <p v-if="calendar.error.value" class="err-line">{{ calendar.error.value }}</p>
            <p v-else-if="calendar.data.value" class="calendar-line mono">
              下次可发：{{ datetime(calendar.data.value.next_publish_time) }}
              （{{ calendar.data.value.immediate ? "立即" : "等待窗口" }}）
            </p>
          </div>

          <div class="job-list">
            <StateBlock v-if="jobs.loading.value && !jobs.loaded.value" kind="loading" title="正在拉取发布任务…" />
            <StateBlock
              v-else-if="jobs.error.value"
              kind="error"
              :title="jobs.offline.value ? '无法连接控制面 API' : '发布任务拉取失败'"
              :detail="jobs.error.value"
            />
            <StateBlock
              v-else-if="jobViews.length === 0"
              kind="empty"
              title="没有发布任务：已成功拉取，后端尚无 PublishJob。用上方「新建任务」创建一条。"
            />
            <div
              v-for="view in jobViews"
              :key="view.job.id"
              class="job-item"
              :class="{ active: view.job.id === selectedJobId }"
              @click="selectJob(view.job.id)"
            >
              <div class="job-item-top">
                <span class="job-id mono" :title="view.job.id">{{ shortId(view.job.id, 10) }}</span>
                <StatusBadge :variant="stateVariant(view.job.state)" :label="PUBLISH_STATE_LABEL[view.job.state]" />
              </div>
              <div class="job-title">{{ view.job.account_id }} → {{ view.job.platform }}</div>
              <div class="job-meta">
                <span>{{ view.job.method }}</span>
                <span>·</span>
                <span class="mono">{{ view.job.scheduled_window }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Detail -->
        <div class="preflight-panel">
          <div class="preflight-header">
            <div>
              <h3 class="panel-title">发布任务详情</h3>
              <span class="job-id-detail mono">{{ selected ? selected.job.id : "—" }}</span>
            </div>
            <StatusBadge
              v-if="selected"
              :variant="stateVariant(selected.job.state)"
              :label="PUBLISH_STATE_LABEL[selected.job.state]"
            />
          </div>

          <div class="preflight-body">
            <p class="fake-note">
              发布执行器为 <strong>Fake</strong>（零 live network，不触真实平台）——真实官方 API / 浏览器 / 真机接入属 stop-condition。
            </p>

            <StateBlock v-if="!selected" kind="empty" title="左侧选择一条发布任务查看详情。" />

            <template v-else>
              <p v-if="actionMsg" class="action-msg" :class="`action-msg--${actionMsg.kind}`">{{ actionMsg.text }}</p>

              <!-- 状态机步条 -->
              <div class="preflight-section">
                <h4 class="detail-label">状态机</h4>
                <div class="state-bar">
                  <div
                    v-for="(st, i) in PUBLISH_MAIN_STATES"
                    :key="st"
                    class="state-step"
                    :class="{ done: mainStateIndex >= i && mainStateIndex >= 0 }"
                  >
                    <span class="state-dot"></span>
                    <span class="state-name">{{ PUBLISH_STATE_LABEL[st] }}</span>
                  </div>
                </div>
                <div v-if="isBranchState" class="state-branch" :class="`branch-${selected.job.state}`">
                  分支状态：{{ PUBLISH_STATE_LABEL[selected.job.state] }}
                  <span v-if="selected.job.state === 'WAITING_FOR_HUMAN'">
                    — 登录失效 / 验证码 / 设备确认 / 内容警告类挑战只能转人工处理，系统不提供任何绕过或自动重试入口。
                  </span>
                </div>
              </div>

              <!-- 发布信息 -->
              <div class="preflight-section">
                <h4 class="detail-label">发布信息</h4>
                <div class="info-grid">
                  <div class="info-item">
                    <span class="info-label">平台 / 方法</span>
                    <span class="info-value">{{ selected.job.platform }} · {{ selected.job.method }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">账号</span>
                    <span class="info-value mono">{{ selected.job.account_id }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">计划窗口</span>
                    <span class="info-value mono">{{ selected.job.scheduled_window }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">幂等键</span>
                    <span class="info-value mono break" :title="selected.job.idempotency_key">
                      {{ shortId(selected.job.idempotency_key, 16) }}
                    </span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">external_post_id</span>
                    <span class="info-value mono break">{{ text(selected.job.external_post_id) }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">external_url</span>
                    <span class="info-value mono break">{{ text(selected.job.external_url) }}</span>
                  </div>
                </div>
              </div>

              <!-- 预检报告 -->
              <div class="preflight-section">
                <h4 class="detail-label">
                  预检报告
                  <span v-if="selected.preflight_report" class="label-sub">
                    · {{ selected.preflight_report.publishable ? "可发布" : "被拦" }}
                  </span>
                </h4>
                <StateBlock
                  v-if="!selected.preflight_report"
                  kind="empty"
                  title="尚未跑过预检。点下方「跑预检」——请求体只传媒体探针，元数据以建任务时入库的那份为准。"
                />
                <div v-else class="checklist">
                  <StateBlock
                    v-if="(selected.preflight_report.findings ?? []).length === 0"
                    kind="empty"
                    title="预检无 finding：16 项检查全部通过。"
                  />
                  <div v-for="(f, i) in selected.preflight_report.findings ?? []" :key="i" class="check-item">
                    <span class="check-icon" :class="`check-${severityClass(f.severity)}`">
                      <svg v-if="severityClass(f.severity) === 'pass'" width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M2 6L5 9L10 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                      <svg v-else width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M3 3L9 9M9 3L3 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
                      </svg>
                    </span>
                    <span class="check-label">{{ f.check }}</span>
                    <span class="check-note" :class="`note-${severityClass(f.severity)}`">{{ f.severity }} · {{ f.detail }}</span>
                  </div>
                </div>
              </div>

              <!-- attempts -->
              <div class="preflight-section">
                <h4 class="detail-label">尝试记录（幂等对账证据）</h4>
                <StateBlock v-if="(selected.job.attempts ?? []).length === 0" kind="empty" title="尚无提交尝试。" />
                <table v-else class="attempt-table">
                  <thead>
                    <tr><th>#</th><th>request_digest</th><th>upload token</th><th>post token</th><th>时间</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="a in selected.job.attempts" :key="a.attempt">
                      <td class="mono">{{ a.attempt }}</td>
                      <td class="mono" :title="a.request_digest">{{ shortId(a.request_digest, 12) }}</td>
                      <td class="mono">{{ text(a.external_upload_token) }}</td>
                      <td class="mono">{{ text(a.external_post_token) }}</td>
                      <td class="mono">{{ datetime(a.at) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div v-if="selected.issues.length" class="preflight-section">
                <h4 class="detail-label">护栏 issues</h4>
                <p v-for="(iss, i) in selected.issues" :key="i" class="err-line">{{ iss }}</p>
              </div>

              <div v-if="selected.job.state === 'WAITING_FOR_HUMAN'" class="preflight-section">
                <h4 class="detail-label">人工完成回填</h4>
                <div class="manual-row">
                  <input v-model="manualPostId" class="form-input mono" type="text" placeholder="人工发布后的 external_post_id" />
                  <button class="btn btn-secondary" :disabled="busy || !manualPostId" @click="doManualComplete">
                    标记人工完成
                  </button>
                </div>
              </div>
            </template>
          </div>

          <div v-if="selected" class="preflight-footer">
            <button class="btn btn-secondary" :disabled="busy" @click="doPreflight">跑预检</button>
            <button class="btn btn-secondary" :disabled="busy" @click="doReconcile" title="查询平台是否已存在该帖子，绝不重发">
              对账
            </button>
            <button
              class="btn btn-primary"
              :disabled="busy || !canSubmit(selected.job)"
              :title="canSubmit(selected.job) ? '提交发布' : '当前状态不可提交（已提交过或非可提交态）'"
              @click="doSubmit"
            >
              提交发布
            </button>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import AppLayout from "@/components/AppLayout.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import StateBlock from "@/components/StateBlock.vue";
import { useAsync } from "@/composables/useAsync";
import { errorText } from "@/api/client";
import {
  canSubmit,
  createPublishJob,
  listPublishJobs,
  manualCompletePublishJob,
  nextPublishTime,
  PUBLISH_MAIN_STATES,
  PUBLISH_STATE_LABEL,
  reconcilePublishJob,
  runPreflight,
  submitPublishJob,
  type NextPublishResponse,
  type PublishJobView,
  type PublishMediaProbe,
  type PublishPlatform,
  type PublishState,
  type ReviewSeverity,
} from "@/api/publish";
import { datetime, shortId, text } from "@/utils/format";

type Variant = "success" | "warning" | "error" | "info" | "neutral";

const jobs = useAsync<PublishJobView[]>();
const calendar = useAsync<NextPublishResponse>();

const selectedJobId = ref<string>("");
const showCreate = ref(false);
const busy = ref(false);
const manualPostId = ref("");
const calendarWindow = ref("immediate");
const actionMsg = ref<{ kind: "ok" | "warn" | "error"; text: string } | null>(null);

// demo 默认值：符合 TikTok/抖音竖屏规格的探针，方便本机跑通闭环
const form = reactive({
  account_id: "demo-account",
  platform: "TIKTOK" as PublishPlatform,
  media_digest: "a".repeat(64),
  title: "Media Atlas 控制台联调样例",
  language: "zh-CN",
  publishing_window: "immediate",
  copy_index: 0,
});

const DEMO_PROBE: PublishMediaProbe = {
  width: 1080,
  height: 1920,
  aspect_ratio: "9:16",
  video_codec: "h264",
  audio_codec: "aac",
  container: "mp4",
  file_size_bytes: 24_000_000,
  duration_ms: 30_000,
};

const jobViews = computed(() => jobs.data.value ?? []);
const selected = computed<PublishJobView | null>(
  () => jobViews.value.find((v) => v.job.id === selectedJobId.value) ?? null,
);

const mainStateIndex = computed(() => {
  const st = selected.value?.job.state;
  if (!st) return -1;
  if (st === "SUCCEEDED_RECONCILED") return PUBLISH_MAIN_STATES.indexOf("SUCCEEDED");
  return PUBLISH_MAIN_STATES.indexOf(st);
});

const isBranchState = computed(() => mainStateIndex.value < 0);

function stateVariant(state: PublishState): Variant {
  switch (state) {
    case "SUCCEEDED":
    case "SUCCEEDED_RECONCILED":
      return "success";
    case "FAILED":
      return "error";
    case "WAITING_FOR_HUMAN":
    case "PREFLIGHT_BLOCKED":
    case "AWAITING_AUTH":
      return "warning";
    case "PENDING":
      return "neutral";
    default:
      return "info";
  }
}

function severityClass(sev: ReviewSeverity): "pass" | "fail" {
  return sev === "INFO" || sev === "WARNING" ? "pass" : "fail";
}

async function reload(): Promise<void> {
  const list = await jobs.run(() => listPublishJobs({ limit: 50 }));
  if (list && list.length > 0 && !list.some((v) => v.job.id === selectedJobId.value)) {
    selectedJobId.value = list[0]!.job.id;
  }
}

function selectJob(id: string): void {
  selectedJobId.value = id;
  actionMsg.value = null;
}

async function loadCalendar(): Promise<void> {
  await calendar.run(() => nextPublishTime(calendarWindow.value.trim() || "immediate"));
}

async function doCreate(): Promise<void> {
  busy.value = true;
  actionMsg.value = null;
  try {
    const job = await createPublishJob({
      account_id: form.account_id,
      platform: form.platform,
      media_digest: form.media_digest,
      metadata: { title: form.title, language: form.language, description: "", tags: [] },
      publishing_window: form.publishing_window,
      copy_index: form.copy_index,
    });
    selectedJobId.value = job.id;
    actionMsg.value = { kind: "ok", text: `已建任务 ${job.id}（幂等键 ${job.idempotency_key}）` };
    await reload();
  } catch (err) {
    actionMsg.value = { kind: "error", text: `建任务失败：${errorText(err)}` };
  } finally {
    busy.value = false;
  }
}

async function doPreflight(): Promise<void> {
  const job = selected.value;
  if (!job) return;
  busy.value = true;
  actionMsg.value = null;
  try {
    // §8：请求体**只传媒体探针**，带 metadata 的旧请求体会被 422 拒
    const res = await runPreflight(job.job.id, DEMO_PROBE);
    actionMsg.value = {
      kind: res.report.publishable ? "ok" : "warn",
      text: res.report.publishable
        ? "预检通过：媒体/元数据/授权/账号全部满足平台规则。"
        : `预检未通过（${(res.report.findings ?? []).filter((f) => f.severity === "ERROR" || f.severity === "FATAL").length} 项阻断），任务已置 PREFLIGHT_BLOCKED。`,
    };
    await reload();
  } catch (err) {
    actionMsg.value = { kind: "error", text: `预检失败：${errorText(err)}` };
  } finally {
    busy.value = false;
  }
}

async function doSubmit(): Promise<void> {
  const job = selected.value;
  if (!job) return;
  busy.value = true;
  actionMsg.value = null;
  try {
    const res = await submitPublishJob(job.job.id);
    actionMsg.value = {
      kind: res.job.state === "WAITING_FOR_HUMAN" ? "warn" : "ok",
      text: `执行器返回 ${res.executor_status}${res.idempotent_replay ? "（幂等重放，未产生第二条帖子）" : ""}${res.detail ? " · " + res.detail : ""}`,
    };
    await reload();
  } catch (err) {
    // 409 = 预检被拦 / 已提交过（幂等硬拦）——detail 原样展示，不提供绕过入口
    actionMsg.value = { kind: "error", text: `提交被拒：${errorText(err)}` };
    await reload();
  } finally {
    busy.value = false;
  }
}

async function doReconcile(): Promise<void> {
  const job = selected.value;
  if (!job) return;
  busy.value = true;
  actionMsg.value = null;
  try {
    const res = await reconcilePublishJob(job.job.id);
    actionMsg.value = {
      kind: "ok",
      text: res.found_post
        ? `对账：平台已存在该帖子（${res.job.external_post_id ?? "—"}），状态置为 ${PUBLISH_STATE_LABEL[res.job.state]} — 未重发。`
        : "对账：平台未查到该帖子，保持核验中继续查——绝不盲目重发。",
    };
    await reload();
  } catch (err) {
    actionMsg.value = { kind: "error", text: `对账失败：${errorText(err)}` };
  } finally {
    busy.value = false;
  }
}

async function doManualComplete(): Promise<void> {
  const job = selected.value;
  if (!job) return;
  busy.value = true;
  actionMsg.value = null;
  try {
    await manualCompletePublishJob(job.job.id, manualPostId.value.trim());
    manualPostId.value = "";
    actionMsg.value = { kind: "ok", text: "已标记人工完成（不新增提交、不再发）。" };
    await reload();
  } catch (err) {
    actionMsg.value = { kind: "error", text: `人工完成失败：${errorText(err)}` };
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  await reload();
  await loadCalendar();
});
</script>

<style scoped>
.publish-view {
  height: 100%;
  overflow: hidden;
}

.publish-content {
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

/* ===== Job Panel ===== */
.job-panel {
  width: 380px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow-y: auto;
}

.job-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.create-form,
.calendar-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.form-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-label {
  min-width: 70px;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
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

.form-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

.calendar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.calendar-title {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.link-btn {
  background: transparent;
  color: var(--color-accent-primary);
  font-size: var(--font-size-xs);
  cursor: pointer;
}

.calendar-line {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.err-line {
  font-size: var(--font-size-xs);
  color: var(--color-status-error);
  line-height: 1.6;
  word-break: break-all;
}

.job-list {
  flex: 1;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.job-item {
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

.job-item:hover {
  border-color: var(--color-border-strong);
}

.job-item.active {
  border-color: var(--color-accent-primary);
  background: rgba(59, 130, 246, 0.05);
}

.job-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.job-id {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.job-title {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  font-weight: 500;
}

.job-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* ===== Detail Panel ===== */
.preflight-panel {
  flex: 1;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preflight-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 20px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.job-id-detail {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.preflight-body {
  flex: 1;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
}

.fake-note {
  font-size: var(--font-size-xs);
  color: var(--color-status-warning);
  background: rgba(245, 166, 35, 0.08);
  border: 1px solid rgba(245, 166, 35, 0.3);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  line-height: 1.6;
}

.action-msg {
  font-size: var(--font-size-base);
  line-height: 1.6;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-primary);
  word-break: break-all;
}

.action-msg--warn {
  color: var(--color-status-warning);
  border-color: rgba(245, 166, 35, 0.4);
}

.action-msg--error {
  color: var(--color-status-error);
  border-color: rgba(239, 68, 68, 0.4);
}

.preflight-section {
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

.label-sub {
  font-weight: 500;
  text-transform: none;
}

/* 状态机步条 */
.state-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.state-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.state-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-status-neutral);
}

.state-step.done {
  color: var(--color-status-success);
  border-color: rgba(60, 207, 78, 0.35);
}

.state-step.done .state-dot {
  background: var(--color-status-success);
}

.state-branch {
  font-size: var(--font-size-xs);
  line-height: 1.6;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  /* WAITING_FOR_HUMAN 用紫色分支色，与成功/警告/错误三态互不混淆 */
  color: #b7a2f5;
  background: rgba(167, 139, 250, 0.1);
  border: 1px solid rgba(167, 139, 250, 0.35);
}

.branch-FAILED {
  color: var(--color-status-error);
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.35);
}

.branch-PREFLIGHT_BLOCKED,
.branch-AWAITING_AUTH {
  color: var(--color-status-warning);
  background: rgba(245, 166, 35, 0.08);
  border-color: rgba(245, 166, 35, 0.35);
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

.check-fail {
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-status-error);
}

.check-label {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
}

.check-note {
  font-size: var(--font-size-xs);
  margin-left: auto;
  text-align: right;
}

.note-fail {
  color: var(--color-status-error);
}

.note-pass {
  color: var(--color-text-tertiary);
}

.attempt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-xs);
}

.attempt-table th {
  text-align: left;
  padding: 8px 10px;
  color: var(--color-text-tertiary);
  background: var(--color-bg-elevated);
  font-weight: 600;
}

.attempt-table td {
  padding: 8px 10px;
  color: var(--color-text-secondary);
  border-top: 1px solid var(--color-border-subtle);
  word-break: break-all;
}

.manual-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.preflight-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid var(--color-border-subtle);
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

.btn-sm {
  height: 30px;
  padding: 0 12px;
  font-size: var(--font-size-sm);
}

.btn-primary {
  background: var(--color-accent-primary);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-accent-primary-hover);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
