<script setup lang="ts">
import { ref, watch } from "vue";

import {
  createProjectFromCluster,
  getCluster,
  rescoreCluster,
  splitCluster,
  type TrendCluster,
} from "../api/trends";
import StageBadge from "./StageBadge.vue";

const props = defineProps<{ clusterId: string }>();
const emit = defineEmits<{ changed: []; projectCreated: [projectId: string] }>();

const cluster = ref<TrendCluster | null>(null);
const error = ref<string | null>(null);
const actionError = ref<string | null>(null);
const message = ref<string | null>(null);
const splitMembers = ref("");

const SUB_LABELS: [keyof NonNullable<TrendCluster["sub_scores"]>, string][] = [
  ["velocity", "速度"],
  ["acceleration", "加速度"],
  ["engagement_efficiency", "互动效率"],
  ["cross_platform_score", "跨平台"],
  ["decay", "衰减"],
  ["saturation", "饱和"],
];

async function load() {
  error.value = null;
  try {
    cluster.value = await getCluster(props.clusterId);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

// 把动作包一层：409（乐观锁冲突）等错误必须提示人工编辑者，别静默吞掉
async function guard(fn: () => Promise<void>) {
  actionError.value = null;
  message.value = null;
  try {
    await fn();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    actionError.value = msg.includes("409")
      ? "该聚类已被他人修改，请刷新后重试（乐观锁冲突）"
      : `操作失败：${msg}`;
    await load(); // 冲突后拉回最新版本，人工可基于新版本重做
  }
}

function doRescore() {
  return guard(async () => {
    if (!cluster.value) return;
    cluster.value = await rescoreCluster(cluster.value.id, cluster.value.version);
    message.value = "已按最新快照重算热度";
    emit("changed");
  });
}

function doSplit() {
  return guard(async () => {
    if (!cluster.value) return;
    const members = splitMembers.value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (members.length === 0) return;
    const result = await splitCluster(cluster.value.id, {
      member_item_ids: members,
      expected_version: cluster.value.version,
      new_title: `${cluster.value.title}（拆分）`,
      new_canonical_topic: `${cluster.value.canonical_topic}-split`,
    });
    cluster.value = result.original;
    splitMembers.value = "";
    message.value = `已拆出新聚类 ${result.created.id.slice(0, 8)}`;
    emit("changed");
  });
}

function doCreateProject() {
  return guard(async () => {
    if (!cluster.value) return;
    const project = await createProjectFromCluster(cluster.value.id, {
      source_language: "zh-CN",
      target_languages: ["en-US"],
      creation_mode: "STRUCTURE_REWRITE",
    });
    message.value = `已创建 Project ${project.id.slice(0, 8)}`;
    emit("projectCreated", project.id);
  });
}

watch(() => props.clusterId, load, { immediate: true });
</script>

<template>
  <aside class="detail">
    <p v-if="error" class="error">{{ error }}</p>
    <template v-else-if="cluster">
      <h2>{{ cluster.title }}</h2>
      <p class="meta">
        <StageBadge :stage="cluster.stage" />
        <span class="hot">热度 {{ cluster.hot_score === null ? "—" : Math.round(cluster.hot_score * 100) }}</span>
        <span>v{{ cluster.version }}</span>
      </p>

      <h3>子分数</h3>
      <ul v-if="cluster.sub_scores" class="subscores">
        <li v-for="[key, label] in SUB_LABELS" :key="key">
          {{ label }}：<b>{{ Math.round(cluster.sub_scores[key] * 100) }}</b>
        </li>
      </ul>
      <p v-else class="empty">尚未评分（附加快照后重算）。</p>

      <h3>理由码</h3>
      <div class="codes">
        <span v-for="rc in cluster.reason_codes" :key="rc" class="code">{{ rc }}</span>
      </div>

      <h3>成员证据（{{ cluster.member_item_ids.length }}）</h3>
      <ul class="members">
        <li v-for="m in cluster.member_item_ids" :key="m">{{ m }}</li>
      </ul>

      <h3>操作</h3>
      <div class="actions">
        <button data-test="rescore" @click="doRescore">重算热度</button>
        <button data-test="create-project" @click="doCreateProject">一键创建 Project</button>
      </div>
      <div class="split">
        <input v-model="splitMembers" placeholder="拆出成员（逗号分隔）" />
        <button data-test="split" @click="doSplit">拆分</button>
      </div>
      <p v-if="actionError" class="error" data-test="action-error">{{ actionError }}</p>
      <p v-if="message" class="message">{{ message }}</p>
    </template>
  </aside>
</template>

<style scoped>
.detail {
  padding: 1rem 1.5rem;
  border-left: 1px solid #eee;
}
.meta {
  display: flex;
  gap: 1rem;
  align-items: center;
  color: #555;
}
.hot {
  font-weight: 700;
}
.subscores,
.members {
  list-style: none;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.code {
  display: inline-block;
  margin: 0.15rem;
  padding: 0.05rem 0.4rem;
  background: #eef;
  border-radius: 6px;
  font-size: 0.72rem;
}
.actions,
.split {
  display: flex;
  gap: 0.5rem;
  margin: 0.5rem 0;
}
.message {
  color: #0a7d33;
}
.error {
  color: #b3261e;
}
.empty {
  color: #666;
}
</style>
