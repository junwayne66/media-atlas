<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo-mark" aria-hidden="true"></div>
        <span class="brand">Media Atlas</span>
      </div>

      <nav class="sidebar-nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
          :aria-current="isActive(item.path) ? 'page' : undefined"
          :title="item.label"
        >
          <span class="nav-icon"><NavIcon :name="item.icon" /></span>
          <span class="nav-label">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar-profile">
        <div class="profile-avatar" aria-hidden="true">U</div>
        <div class="profile-copy">
          <span class="profile-name">Local User</span>
          <span class="profile-mode">LOCAL CONSOLE</span>
        </div>
      </div>
    </aside>

    <div class="main-area">
      <header class="top-bar">
        <div class="top-left">
          <slot name="breadcrumb">
            <span class="breadcrumb">{{ activeNavLabel }}</span>
          </slot>
        </div>

        <div class="top-right">
          <div class="api-health" :class="`api-health--${healthState}`" :title="healthTitle">
            <span class="api-dot"></span>
            <span class="api-text">{{ healthLabel }}</span>
          </div>
          <button
            type="button"
            class="icon-btn"
            :aria-label="isDark ? '切换到浅色主题' : '切换到深色主题'"
            :aria-pressed="isDark"
            title="切换主题 (Ctrl+Shift+L)"
            @click="toggleTheme"
          >
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
              <circle cx="8" cy="8" r="3.25" />
              <path d="M8 1.5v1.4M8 13.1v1.4M1.5 8h1.4M13.1 8h1.4M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
            </svg>
          </button>
          <button type="button" class="account-avatar" aria-label="本地账户"></button>
        </div>
      </header>

      <main class="content-area">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { errorText } from "@/api/client";
import { getHealth } from "@/api/health";
import NavIcon from "@/components/NavIcon.vue";
import { useTheme } from "@/composables/useTheme";

type NavIconName =
  | "dashboard"
  | "hotspots"
  | "library"
  | "blueprint"
  | "script"
  | "localization"
  | "review"
  | "publish"
  | "stats"
  | "settings";

interface NavItem {
  path: string;
  label: string;
  icon: NavIconName;
}

type HealthState = "checking" | "ok" | "down";

const route = useRoute();
const { isDark, toggleTheme } = useTheme();
const healthState = ref<HealthState>("checking");
const healthTitle = ref("正在探测控制面 API…");
let healthTimer: number | undefined;

const navItems: NavItem[] = [
  { path: "/dashboard", label: "项目工作台", icon: "dashboard" },
  { path: "/hotspots", label: "热点池", icon: "hotspots" },
  { path: "/library", label: "素材库", icon: "library" },
  { path: "/blueprint", label: "创作编辑", icon: "blueprint" },
  { path: "/script-editor", label: "脚本编辑", icon: "script" },
  { path: "/localization", label: "本地化", icon: "localization" },
  { path: "/review", label: "审核中心", icon: "review" },
  { path: "/publish", label: "发布", icon: "publish" },
  { path: "/stats", label: "效果看板", icon: "stats" },
  { path: "/settings", label: "系统与设置", icon: "settings" },
];

const healthLabel = computed(() => {
  if (healthState.value === "ok") return "API ONLINE";
  if (healthState.value === "down") return "API OFFLINE";
  return "API CHECKING";
});

const activeNavLabel = computed(() => {
  const item = navItems.find((candidate) => isActive(candidate.path));
  return item?.label ?? String(route.meta.title ?? "项目工作台");
});

function isActive(path: string): boolean {
  return route.path === path;
}

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
</script>

<style scoped>
.app-layout {
  display: flex;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 50% 50%, rgba(0, 40, 60, 0.2), transparent 62%),
    var(--color-bg-primary);
}

.sidebar {
  width: var(--sidebar-width);
  height: 100%;
  background: var(--color-bg-sidebar);
  border-right: 1px solid var(--color-border-subtle);
  box-shadow: 4px 0 24px rgba(0, 204, 255, 0.08);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  z-index: var(--z-sidebar);
}

.sidebar-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border-bottom: 1px solid rgba(0, 255, 255, 0.1);
  flex-shrink: 0;
}

.logo-mark {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #3ba6ff, #6e6eff);
  position: relative;
  flex-shrink: 0;
  box-shadow: 0 0 10px rgba(59, 166, 255, 0.2);
}

.logo-mark::before,
.logo-mark::after {
  content: "";
  position: absolute;
  left: 8px;
  right: 8px;
  height: 2px;
  background: #fff;
  border-radius: 1px;
}

.logo-mark::before {
  top: 10px;
}

.logo-mark::after {
  top: 14px;
}

.brand {
  color: var(--color-text-primary);
  font-size: var(--font-size-2xl);
  font-weight: 600;
  white-space: nowrap;
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px;
  overflow-y: auto;
}

.nav-item {
  min-height: 34px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-base);
  font-weight: 500;
}

.nav-item:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.03);
}

.nav-item.active {
  color: var(--color-accent-primary);
  background: var(--color-bg-elevated);
  border-color: rgba(0, 255, 255, 0.3);
  box-shadow:
    inset 0 0 8px rgba(0, 255, 255, 0.15),
    0 0 12px rgba(0, 255, 255, 0.1);
  font-weight: 600;
}

.nav-icon {
  width: 16px;
  height: 16px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.nav-icon svg {
  width: 16px;
  height: 16px;
}

.nav-label {
  line-height: 1;
}

.sidebar-profile {
  min-height: 56px;
  padding: 0 16px;
  border-top: 1px solid rgba(0, 255, 255, 0.1);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.profile-avatar {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f4, #7070f2);
  color: #fff;
  font-weight: 600;
  flex-shrink: 0;
}

.profile-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.profile-name {
  color: var(--color-text-primary);
  font-size: var(--font-size-sm);
}

.profile-mode {
  color: var(--color-text-tertiary);
  font-family: var(--font-family-mono);
  font-size: 9px;
  letter-spacing: 0.06em;
}

.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.top-bar {
  height: var(--topbar-height);
  padding: 0 16px;
  border-bottom: 1px solid rgba(0, 255, 255, 0.1);
  background: var(--color-bg-sidebar);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  z-index: var(--z-topbar);
}

.top-left,
.top-right {
  display: flex;
  align-items: center;
  min-width: 0;
}

.top-right {
  gap: 8px;
  flex-shrink: 0;
}

.breadcrumb {
  color: var(--color-text-primary);
  font-size: var(--font-size-base);
  font-weight: 600;
}

.api-health {
  height: 28px;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: var(--radius-sm);
}

.api-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-status-success);
  box-shadow: var(--glow-green);
}

.api-text {
  color: var(--color-status-success);
  font-family: var(--font-family-mono);
  font-size: var(--font-size-xs);
  letter-spacing: 0.05em;
}

.api-health--checking .api-dot {
  background: var(--color-status-neutral);
  box-shadow: none;
}

.api-health--checking .api-text {
  color: var(--color-status-neutral);
}

.api-health--down .api-dot {
  background: var(--color-status-error);
  box-shadow: 0 0 6px rgba(255, 51, 102, 0.5);
}

.api-health--down .api-text {
  color: var(--color-status-error);
}

.icon-btn {
  width: 32px;
  height: 32px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  display: grid;
  place-items: center;
  color: var(--color-accent-primary);
  background: var(--color-bg-elevated);
}

.icon-btn:hover {
  border-color: var(--color-accent-primary);
  box-shadow: var(--glow-cyan-sm);
}

.icon-btn svg {
  width: 15px;
  height: 15px;
}

.account-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-accent-primary), var(--color-accent-magenta));
  box-shadow: var(--glow-cyan-sm);
  flex-shrink: 0;
}

.content-area {
  flex: 1;
  min-width: 0;
  overflow: auto;
}

@media (max-width: 900px) {
  .sidebar {
    width: 64px;
  }

  .sidebar-header {
    justify-content: center;
  }

  .brand,
  .nav-label,
  .profile-copy {
    display: none;
  }

  .sidebar-nav {
    padding: 12px 10px;
  }

  .nav-item {
    justify-content: center;
    padding: 0;
  }

  .sidebar-profile {
    justify-content: center;
    padding: 0;
  }
}

@media (max-width: 480px) {
  .sidebar {
    width: 56px;
  }

  .api-text {
    display: none;
  }

  .api-health {
    padding: 4px;
  }

  .top-bar {
    padding: 0 10px;
  }
}
</style>
