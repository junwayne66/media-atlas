<template>
  <AppLayout>
    <div class="blueprint-view">
      <!-- Tab Bar -->
      <div class="tab-bar">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-item"
          :class="{ active: tab.key === activeTab }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
        <div class="tab-spacer"></div>
        <span class="engine-note">分析引擎为 Fake（录制 fixtures），非真实模型输出</span>
        <div v-if="issueCount > 0" class="issue-indicator">
          <span class="issue-dot"></span>
          <span class="issue-text">{{ issueCount }} 个待处理问题</span>
        </div>
      </div>

      <!-- Stage strip: 缓存证据（cache_key / 命中缓存） -->
      <div v-if="run" class="stage-strip">
        <div v-for="s in run.stages" :key="s.stage" class="stage-chip" :title="s.cache_key ?? '无 cache_key'">
          <span class="stage-chip-name">{{ s.stage }}</span>
          <span class="stage-chip-status" :class="s.error ? 'chip-error' : 'chip-ok'">{{ s.error ? "失败" : s.status }}</span>
          <span class="stage-chip-cache">{{ s.cache_hit ? "命中缓存" : "重新计算" }}</span>
        </div>
      </div>

      <!-- Blueprint Content -->
      <div class="blueprint-content">
        <!-- Left: item list -->
        <div class="scene-panel">
          <div class="panel-head">
            <h3 class="panel-title">{{ listTitle }}</h3>
            <select v-model="selectedProjectId" class="project-select">
              <option value="">选择项目…</option>
              <option v-for="p in projects.data.value ?? []" :key="p.id" :value="p.id">{{ p.title }}</option>
            </select>
          </div>

          <StateBlock v-if="!selectedProjectId" kind="empty" title="请先选择一个项目。" />
          <StateBlock v-else-if="artifact.loading.value" kind="loading" title="正在拉取分析产物…" />
          <StateBlock
            v-else-if="artifact.notFound.value"
            kind="empty"
            title="该项目还没有分析产物。"
            :detail="artifact.error.value"
          >
            <div class="run-form">
              <select v-model="runAssetId" class="project-select">
                <option value="">选择本地素材…</option>
                <option v-for="a in projectAssets" :key="a.id" :value="a.id">
                  {{ a.local_path ?? a.canonical_url ?? a.original_input }}
                </option>
              </select>
              <button class="run-btn" :disabled="!runAssetId || running" @click="startAnalysis">
                {{ running ? "发起中…" : "发起分析" }}
              </button>
            </div>
            <p v-if="projectAssets.length === 0" class="run-hint">
              该项目没有关联素材。请先在「素材库」导入本地文件并关联到本项目——无本地文件时后端会以 409 拒绝分析（诚实，不假装分析）。
            </p>
            <p v-if="runError" class="run-error">{{ runError }}</p>
          </StateBlock>
          <StateBlock
            v-else-if="artifact.error.value"
            kind="error"
            title="分析产物拉取失败"
            :detail="artifact.error.value"
          />
          <StateBlock v-else-if="items.length === 0" kind="empty" :title="`已拉取到产物，但${listTitle}为空。`" />
          <div
            v-for="(item, i) in items"
            :key="item.key"
            class="scene-item"
            :class="{ active: i === activeIndex }"
            @click="activeIndex = i"
          >
            <span class="scene-num mono">{{ String(i + 1).padStart(2, "0") }}</span>
            <div class="scene-info">
              <span class="scene-time mono">{{ item.time }}</span>
              <span class="scene-desc" :class="{ 'is-flagged': item.flagged }">{{ item.desc }}</span>
            </div>
          </div>
        </div>

        <!-- Right: detail -->
        <div class="detail-panel">
          <div class="detail-header">
            <div>
              <h3 class="panel-title">{{ activeItem ? activeItem.title : "详情" }}</h3>
              <span class="scene-timecode mono">{{ activeItem ? activeItem.time : "—" }}</span>
            </div>
            <StatusBadge
              v-if="activeItem"
              :variant="activeItem.badgeVariant"
              :label="activeItem.badgeLabel"
            />
          </div>

          <div v-if="activeItem" class="detail-body">
            <div v-for="section in activeItem.sections" :key="section.label" class="detail-section">
              <h4 class="detail-label">{{ section.label }}</h4>
              <p class="detail-text" :class="{ 'text-disputed': section.disputed }">{{ section.value }}</p>
            </div>
            <div v-if="activeItem.markers.length" class="detail-section">
              <h4 class="detail-label">标记</h4>
              <div class="markers">
                <span v-for="m in activeItem.markers" :key="m.text" class="marker" :class="`marker-${m.tone}`">
                  {{ m.text }}
                </span>
              </div>
            </div>
          </div>
          <StateBlock v-else kind="empty" title="左侧选择一项查看详情。" />
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
import { errorText } from "@/api/client";
import { getLatestAnalysis, listProjects, runAnalysis, type AnalysisRunView, type Project } from "@/api/projects";
import { listSources, type SourceAsset } from "@/api/sources";
import {
  fetchBlueprint,
  fetchTextTracks,
  fetchTranscript,
  fetchVisual,
  type TextTrackSet,
  type Transcript,
  type VideoBlueprint,
  type VisualAnalysis,
} from "@/api/analysis";
import { timecode } from "@/utils/format";

type Variant = "success" | "warning" | "error" | "info" | "neutral";
type TabKey = "transcript" | "texttracks" | "visual" | "blueprint";

interface ListItem {
  key: string;
  time: string;
  desc: string;
  flagged: boolean;
  title: string;
  badgeVariant: Variant;
  badgeLabel: string;
  sections: { label: string; value: string; disputed?: boolean }[];
  markers: { text: string; tone: "info" | "warning" | "error" }[];
}

const { selectedProjectId } = useSelectedProject();

const projects = useAsync<Project[]>();
const analysis = useAsync<AnalysisRunView>();
const sources = useAsync<SourceAsset[]>();
const artifact = useAsync<Transcript | TextTrackSet | VisualAnalysis | VideoBlueprint>();

const tabs: { key: TabKey; label: string }[] = [
  { key: "transcript", label: "转写稿" },
  { key: "texttracks", label: "字幕轨" },
  { key: "visual", label: "画面分析" },
  { key: "blueprint", label: "蓝图" },
];

const activeTab = ref<TabKey>("blueprint");
const activeIndex = ref(0);
const runAssetId = ref("");
const running = ref(false);
const runError = ref<string | null>(null);

const run = computed(() => analysis.data.value);

const listTitle = computed(() => {
  switch (activeTab.value) {
    case "transcript":
      return "转写分段";
    case "texttracks":
      return "画面文字轨";
    case "visual":
      return "采样帧";
    default:
      return "节拍与 Claim";
  }
});

const projectAssets = computed(() =>
  (sources.data.value ?? []).filter(
    (a) => (a.project_ids ?? []).includes(selectedProjectId.value) && a.local_path,
  ),
);

const issueCount = computed(() =>
  (run.value?.stages ?? []).reduce((n, s) => n + s.issues.length + (s.error ? 1 : 0), 0),
);

const items = computed<ListItem[]>(() => {
  const data = artifact.data.value;
  if (!data) return [];
  switch (activeTab.value) {
    case "transcript":
      return transcriptItems(data as Transcript);
    case "texttracks":
      return textTrackItems(data as TextTrackSet);
    case "visual":
      return visualItems(data as VisualAnalysis);
    default:
      return blueprintItems(data as VideoBlueprint);
  }
});

const activeItem = computed<ListItem | null>(() => items.value[activeIndex.value] ?? null);

function transcriptItems(t: Transcript): ListItem[] {
  return (t.segments ?? []).map((seg) => ({
    key: seg.id,
    time: `${timecode(seg.start_ms)} → ${timecode(seg.end_ms)}`,
    desc: seg.text || "(空段)",
    flagged: seg.low_confidence ?? false,
    title: `转写段 ${seg.id}`,
    badgeVariant: seg.low_confidence ? "warning" : "success",
    badgeLabel: seg.low_confidence ? "低置信" : `置信 ${seg.confidence.toFixed(2)}`,
    sections: [
      { label: "文本", value: seg.text || "(空)" },
      { label: "语言 / 说话人", value: `${seg.language} · ${seg.speaker_id ?? "—"}` },
      {
        label: "逐词时间戳",
        value:
          (seg.words ?? [])
            .map((w) => `${w.text}[${w.start_ms}-${w.end_ms}${w.low_confidence ? "!" : ""}]`)
            .join(" ") || "—",
      },
    ],
    markers: (seg.words ?? [])
      .filter((w) => w.low_confidence)
      .slice(0, 12)
      .map((w) => ({ text: `低置信词: ${w.text}`, tone: "warning" as const })),
  }));
}

function textTrackItems(s: TextTrackSet): ListItem[] {
  return (s.tracks ?? []).map((tr) => ({
    key: tr.id,
    time: `${timecode(tr.start_ms)} → ${timecode(tr.end_ms)}`,
    desc: tr.text || "(空)",
    flagged: tr.low_confidence ?? false,
    title: `${tr.kind ?? "UNKNOWN"} · ${tr.id}`,
    badgeVariant: tr.low_confidence ? "warning" : "info",
    badgeLabel: tr.low_confidence ? "低置信" : (tr.kind ?? "UNKNOWN"),
    sections: [
      { label: "投票文本", value: tr.text || "(空)" },
      { label: "类型 / 运动", value: `${tr.kind ?? "UNKNOWN"} · ${tr.motion ?? "—"}` },
      { label: "置信度", value: tr.confidence.toFixed(3) },
      { label: "OCR 引擎", value: `${s.ocr_provider} ${s.ocr_version ?? ""}`.trim() },
    ],
    markers: [],
  }));
}

function visualItems(v: VisualAnalysis): ListItem[] {
  return (v.frames ?? []).map((f, i) => ({
    key: `frame-${i}-${f.frame_time_ms}`,
    time: timecode(f.frame_time_ms),
    // caption 为 null 显示"未分析"（诚实，不编造）
    desc: f.caption ?? "未分析",
    flagged: f.caption === null,
    title: `采样帧 @ ${timecode(f.frame_time_ms)}`,
    badgeVariant: f.caption === null ? "neutral" : "info",
    badgeLabel: f.caption === null ? "未分析" : "已分析",
    sections: [
      { label: "描述", value: f.caption ?? "未分析（选中但 VLM 未产出 caption）" },
      { label: "采样理由", value: f.reasons.join(" · ") },
      { label: "标签", value: (f.labels ?? []).join(" · ") || "—" },
      { label: "置信度", value: f.confidence == null ? "—" : f.confidence.toFixed(3) },
      { label: "采样策略 / VLM", value: `${v.sampling_policy} · ${v.vlm_provider ?? "未接入"}` },
    ],
    markers: f.reasons.map((r) => ({ text: r, tone: "info" as const })),
  }));
}

function blueprintItems(b: VideoBlueprint): ListItem[] {
  const claimById = new Map((b.claims ?? []).map((c) => [c.id, c]));
  const beats: ListItem[] = (b.rhetorical_beats ?? []).map((beat) => {
    const claims = (beat.claim_ids ?? []).map((id) => claimById.get(id)).filter((c) => c !== undefined);
    const disputed = claims.some((c) => c.source_status === "DISPUTED");
    return {
      key: beat.id,
      time: `${timecode(beat.start_ms)} → ${timecode(beat.end_ms)}`,
      desc: `${beat.kind}${beat.summary ? " · " + beat.summary : ""}`,
      flagged: disputed,
      title: `节拍 ${beat.kind}`,
      badgeVariant: disputed ? "error" : "info",
      badgeLabel: disputed ? "含 DISPUTED Claim" : beat.kind,
      sections: [
        { label: "摘要", value: beat.summary ?? "—" },
        {
          label: "Claim",
          value: claims.map((c) => `[${c.source_status}] ${c.text}`).join("\n") || "—",
          disputed,
        },
        {
          label: "证据链",
          value:
            claims
              .flatMap((c) => c.evidence.map((e) => `${e.kind}:${e.ref_id} ${timecode(e.start_ms)}-${timecode(e.end_ms)}`))
              .join("\n") || "—",
        },
      ],
      markers: claims.map((c) => ({
        text: `${c.id} · ${c.source_status}`,
        tone: c.source_status === "DISPUTED" ? ("error" as const) : ("info" as const),
      })),
    };
  });
  const visual: ListItem[] = (b.visual_beats ?? []).map((vb) => ({
    key: vb.id,
    time: `${timecode(vb.start_ms)} → ${timecode(vb.end_ms)}`,
    desc: `视觉节拍 · ${vb.kind}`,
    flagged: false,
    title: `视觉节拍 ${vb.kind}`,
    badgeVariant: "neutral",
    badgeLabel: vb.kind,
    sections: [
      { label: "代表帧", value: vb.frame_time_ms == null ? "—" : timecode(vb.frame_time_ms) },
      { label: "融合引擎", value: b.fusion_provider ?? "未接入" },
      { label: "覆盖率", value: b.coverage == null ? "—" : b.coverage.toFixed(3) },
    ],
    markers: [],
  }));
  return [...beats, ...visual];
}

function loadArtifact(): Promise<unknown> {
  const id = selectedProjectId.value;
  activeIndex.value = 0;
  if (!id) {
    artifact.reset();
    return Promise.resolve(null);
  }
  switch (activeTab.value) {
    case "transcript":
      return artifact.run(() => fetchTranscript(id));
    case "texttracks":
      return artifact.run(() => fetchTextTracks(id));
    case "visual":
      return artifact.run(() => fetchVisual(id));
    default:
      return artifact.run(() => fetchBlueprint(id));
  }
}

function switchTab(key: TabKey): void {
  activeTab.value = key;
  void loadArtifact();
}

async function reloadProject(): Promise<void> {
  const id = selectedProjectId.value;
  if (!id) return;
  await analysis.run(() => getLatestAnalysis(id));
  await loadArtifact();
}

async function startAnalysis(): Promise<void> {
  const id = selectedProjectId.value;
  if (!id || !runAssetId.value) return;
  running.value = true;
  runError.value = null;
  const project = (projects.data.value ?? []).find((p) => p.id === id);
  try {
    await runAnalysis(id, {
      source_asset_id: runAssetId.value,
      language: project?.source_language ?? "zh-CN",
    });
    await reloadProject();
  } catch (err) {
    // 409（无本地文件素材）/ 422（语言不支持）detail 原样展示
    runError.value = errorText(err);
  } finally {
    running.value = false;
  }
}

watch(selectedProjectId, () => void reloadProject());

onMounted(async () => {
  const [list] = await Promise.all([projects.run(() => listProjects(50)), sources.run(() => listSources({ limit: 200 }))]);
  if (!selectedProjectId.value && list && list.length > 0) {
    selectedProjectId.value = list[0]!.id;
  } else {
    await reloadProject();
  }
});
</script>

<style scoped>
.blueprint-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ===== Tab Bar ===== */
.tab-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 44px;
  padding: 0 16px;
  background: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border-subtle);
  flex-shrink: 0;
}

.tab-item {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 32px;
  padding: 0 12px;
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--color-text-secondary);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms ease;
}

.tab-item:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.tab-item.active {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-accent-primary);
  color: var(--color-text-primary);
}

.tab-spacer {
  flex: 1;
}

.engine-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-right: 12px;
}

.issue-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(245, 166, 35, 0.1);
  border: 1px solid rgba(245, 166, 35, 0.3);
  border-radius: var(--radius-sm);
}

.issue-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-status-warning);
}

.issue-text {
  font-size: var(--font-size-xs);
  color: var(--color-status-warning);
}

/* ===== Stage strip ===== */
.stage-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 24px 0;
  flex-shrink: 0;
}

.stage-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.stage-chip-name {
  color: var(--color-text-primary);
  font-weight: 600;
}

.chip-ok {
  color: var(--color-status-success);
}

.chip-error {
  color: var(--color-status-error);
}

.stage-chip-cache {
  color: var(--color-text-tertiary);
}

/* ===== Blueprint Content ===== */
.blueprint-content {
  flex: 1;
  display: flex;
  gap: 20px;
  padding: 24px;
  overflow: hidden;
}

.scene-panel {
  width: 340px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex-shrink: 0;
}

.panel-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
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

.panel-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.run-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.run-btn {
  height: 30px;
  padding: 0 12px;
  font-size: var(--font-size-xs);
  font-weight: 500;
  color: var(--color-accent-primary);
  background: rgba(0, 255, 255, 0.08);
  border: 1px solid rgba(0, 255, 255, 0.3);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.run-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.run-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  line-height: 1.6;
}

.run-error {
  font-size: var(--font-size-xs);
  color: var(--color-status-error);
  line-height: 1.6;
  word-break: break-all;
}

.scene-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 150ms ease;
}

.scene-item:hover {
  background: var(--color-bg-hover);
}

.scene-item.active {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-accent-primary);
}

.scene-num {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-text-tertiary);
  min-width: 24px;
}

.scene-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.scene-time {
  font-size: var(--font-size-xs);
  color: var(--color-accent-primary);
}

.scene-desc {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
}

.scene-desc.is-flagged {
  color: var(--color-status-warning);
}

/* ===== Detail Panel ===== */
.detail-panel {
  flex: 1;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.scene-timecode {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-label {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.detail-text {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.text-disputed {
  color: var(--color-status-error);
}

.markers {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.marker {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: 500;
}

.marker-info {
  background: rgba(0, 255, 255, 0.08);
  color: var(--color-status-info);
}

.marker-warning {
  background: rgba(245, 166, 35, 0.1);
  color: var(--color-status-warning);
}

.marker-error {
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-status-error);
}
</style>
