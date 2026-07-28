<template>
  <n-config-provider :theme="themeOverride" :theme-overrides="themeOverrides">
    <router-view />
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { darkTheme, type GlobalThemeOverrides } from "naive-ui";
import { useTheme } from "@/composables/useTheme";

const { isDark, toggleTheme } = useTheme();

const themeOverride = computed(() => (isDark.value ? darkTheme : null));

const themeOverrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: "#00FFFF",
    primaryColorHover: "#66FFFF",
    primaryColorPressed: "#00CCCC",
    borderRadius: "6px",
    fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontFamilyMono: '"Geist Mono", "JetBrains Mono", "SF Mono", monospace',
    bodyColor: "var(--color-bg-primary)",
    cardColor: "var(--color-bg-card)",
    modalColor: "var(--color-bg-card)",
    popoverColor: "var(--color-bg-card)",
    textColorBase: "var(--color-text-primary)",
    textColor1: "var(--color-text-primary)",
    textColor2: "var(--color-text-secondary)",
    textColor3: "var(--color-text-tertiary)",
    dividerColor: "var(--color-border-subtle)",
    borderColor: "var(--color-border-strong)",
    inputColor: "var(--color-bg-elevated)",
    actionColor: "var(--color-bg-hover)",
    tableColor: "var(--color-bg-card)",
    tableHeaderColor: "var(--color-bg-elevated)",
  },
}));

function handleThemeShortcut(e: KeyboardEvent): void {
  if (e.ctrlKey && e.shiftKey && e.key === "L") {
    e.preventDefault();
    toggleTheme();
  }
}

onMounted(() => window.addEventListener("keydown", handleThemeShortcut));
onUnmounted(() => window.removeEventListener("keydown", handleThemeShortcut));
</script>

<style scoped></style>
