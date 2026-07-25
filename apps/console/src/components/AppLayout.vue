<template>
  <div class="app-layout">
    <!-- Sidebar (220px) -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo">
          <img :src="logoSvg" alt="" />
        </div>
        <span class="brand">Media Atlas</span>
      </div>

      <nav class="sidebar-nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >
          <img :src="item.icon" alt="" class="nav-icon" />
          <span class="nav-label">{{ item.label }}</span>
          <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
        </RouterLink>
      </nav>
    </aside>

    <!-- Main Area -->
    <div class="main-area">
      <!-- Top Bar (48px) -->
      <header class="top-bar">
        <div class="top-left">
          <slot name="breadcrumb">
            <span class="bc-item">{{ activeNavLabel }}</span>
          </slot>
        </div>
        <div class="top-right">
          <div class="api-health" :class="`api-health--${healthState}`" :title="healthTitle">
            <span class="api-dot"></span>
            <span class="api-text">{{ healthLabel }}</span>
          </div>
          <div class="theme-toggle" @click="toggleTheme" title="切换主题 (Ctrl+Shift+L)">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path
                d="M7 0.583C7 0.583 7 1.75 7 3.5M7 13.417C7 13.417 7 12.25 7 10.5M4.125 1.75C4.125 1.75 4.708 2.333 5.542 3.5M9.875 12.25C9.875 12.25 9.292 11.667 8.458 10.5M1.75 4.125C1.75 4.125 2.333 4.708 3.5 5.542M12.25 9.875C12.25 9.875 11.667 9.292 10.5 8.458M0.583 7C0.583 7 1.75 7 3.5 7M13.417 7C13.417 7 12.25 7 10.5 7"
                stroke="currentColor"
                stroke-width="1.2"
                stroke-linecap="round"
              />
            </svg>
          </div>
          <div class="account">Z</div>
        </div>
      </header>

      <!-- Content Area -->
      <main class="content-area">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { getHealth } from "@/api/health";
import { errorText } from "@/api/client";

const route = useRoute();
const isDark = ref(true);

// —— API 健康徽章（docs/modules/45 §0.1：GET /healthz）——
type HealthState = "checking" | "ok" | "down";
const healthState = ref<HealthState>("checking");
const healthTitle = ref("正在探测控制面 API…");
let healthTimer: number | undefined;

const healthLabel = computed(() => {
  if (healthState.value === "ok") return "API 正常";
  if (healthState.value === "down") return "API 不可用";
  return "API 探测中";
});

async function probeHealth(): Promise<void> {
  try {
    const health = await getHealth();
    healthState.value = health.status === "ok" ? "ok" : "down";
    healthTitle.value = `${health.service} v${health.version} · status=${health.status}`;
  } catch (err) {
    healthState.value = "down";
    healthTitle.value = errorText(err);
  }
}

onMounted(() => {
  void probeHealth();
  healthTimer = window.setInterval(() => void probeHealth(), 30_000);
});

onUnmounted(() => {
  if (healthTimer !== undefined) window.clearInterval(healthTimer);
});

const logoSvg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 28 28'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%233B82F6'/%3E%3Cstop offset='1' stop-color='%236F6FF2'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='28' height='28' rx='6' fill='url(%23g)'/%3E%3C/svg%3E";

const navItems = [
  { path: "/hotspots", label: "热点池", icon: iconUrl("2_70"), badge: "" },
  { path: "/library", label: "素材库", icon: iconUrl("2_73"), badge: "" },
  // badge 留空：没有真实计数来源前不摆假数字（§0.2 红线：不假装真数据）
  { path: "/dashboard", label: "项目", icon: iconUrl("2_78"), badge: "" },
  { path: "/review", label: "审核", icon: iconUrl("2_80"), badge: "" },
  { path: "/publish", label: "发布", icon: iconUrl("2_82"), badge: "" },
  { path: "/stats", label: "效果", icon: iconUrl("2_84"), badge: "" },
  { path: "/settings", label: "设置", icon: iconUrl("2_86"), badge: "" },
];

function iconUrl(name: string): string {
  return new URL(`../assets/svg/${name}.svg`, import.meta.url).href;
}

const isActive = (path: string) => {
  if (path === "/dashboard" && (route.path === "/dashboard" || route.path === "/blueprint" || route.path === "/script-editor" || route.path === "/localization")) return true;
  return route.path === path;
};

const activeNavLabel = computed(() => {
  const item = navItems.find((i) => isActive(i.path));
  return item ? item.label : route.meta.title || "项目";
});

function toggleTheme() {
  isDark.value = !isDark.value;
  document.documentElement.setAttribute("data-theme", isDark.value ? "dark" : "light");
}
</script>

<style scoped>
.app-layout {
  display: flex;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: var(--color-bg-primary);
}

/* ===== Sidebar ===== */
.sidebar {
  width: var(--sidebar-width);
  height: 100%;
  background: var(--color-bg-sidebar);
  border-right: 1px solid var(--color-border-subtle);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  z-index: var(--z-sidebar);
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 16px;
}

.logo {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-md);
  overflow: hidden;
  flex-shrink: 0;
}

.logo img {
  width: 100%;
  height: 100%;
}

.brand {
  font-size: var(--font-size-2xl);
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 12px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 34px;
  padding: 0 8px;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  font-weight: 500;
  transition: all 150ms ease;
  cursor: pointer;
}

.nav-item:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.nav-item.active {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-weight: 600;
}

.nav-item.active .nav-icon {
  opacity: 1;
  filter: brightness(1.3);
}

.nav-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  opacity: 0.7;
  transition: opacity 150ms ease;
}

.nav-label {
  flex: 1;
}

.nav-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 18px;
  padding: 0 4px;
  background: var(--color-accent-primary);
  color: #fff;
  font-size: 10px;
  font-family: var(--font-family-mono);
  font-weight: 500;
  border-radius: var(--radius-sm);
  line-height: 1;
}

.nav-item:not(.active) .nav-badge {
  background: var(--color-border-strong);
  color: var(--color-text-secondary);
}

/* ===== Main Area ===== */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

/* ===== Top Bar ===== */
.top-bar {
  height: var(--topbar-height);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  gap: 12px;
  flex-shrink: 0;
  z-index: var(--z-topbar);
}

.top-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.bc-item {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.top-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.api-health {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}

.api-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-status-success);
}

.api-text {
  font-size: var(--font-size-xs);
  font-weight: 500;
  color: var(--color-status-success);
}

.api-health--checking .api-dot {
  background: var(--color-status-neutral);
}

.api-health--checking .api-text {
  color: var(--color-status-neutral);
}

.api-health--down .api-dot {
  background: var(--color-status-error);
}

.api-health--down .api-text {
  color: var(--color-status-error);
}

.theme-toggle {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 150ms ease;
}

.theme-toggle:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.account {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #3B82F6, #6F6FF2);
  color: #fff;
  font-size: var(--font-size-base);
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
}

/* ===== Content Area ===== */
.content-area {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
