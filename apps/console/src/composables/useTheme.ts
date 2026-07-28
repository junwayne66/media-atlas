import { computed, ref } from "vue";

const isDark = ref(document.documentElement.dataset.theme !== "light");

function applyTheme(): void {
  document.documentElement.dataset.theme = isDark.value ? "dark" : "light";
}

export function useTheme() {
  const themeName = computed(() => (isDark.value ? "dark" : "light"));

  function toggleTheme(): void {
    isDark.value = !isDark.value;
    applyTheme();
  }

  applyTheme();
  return { isDark, themeName, toggleTheme };
}
