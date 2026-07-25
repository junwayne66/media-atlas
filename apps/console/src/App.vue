<template>
  <n-config-provider :theme="themeOverride" :theme-overrides="themeOverrides">
    <router-view />
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { darkTheme, type GlobalThemeOverrides } from "naive-ui";

const isDark = ref(true);

const themeOverride = computed(() => (isDark.value ? darkTheme : null));

const themeOverrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: "#3B82F6",
    primaryColorHover: "#4D8DF9",
    primaryColorPressed: "#3574D4",
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

// Toggle theme via keyboard shortcut: Ctrl+Shift+L
window.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.shiftKey && e.key === "L") {
    isDark.value = !isDark.value;
    document.documentElement.setAttribute("data-theme", isDark.value ? "dark" : "light");
  }
});
</script>

<style scoped></style>
