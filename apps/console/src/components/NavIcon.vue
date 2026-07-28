<template>
  <svg
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    stroke-width="1.4"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'dashboard'">
      <rect x="2" y="2" width="4.67" height="4.67" />
      <rect x="9.33" y="2" width="4.67" height="4.67" />
      <rect x="2" y="9.33" width="4.67" height="4.67" />
      <rect x="9.33" y="9.33" width="4.67" height="4.67" />
    </template>
    <path
      v-else-if="name === 'hotspots'"
      d="M2.67 11.33c0-2.67 2.67-4 2.67-6.67 0-1.33 1.33-2.67 1.33-2.67s2.67 1.34 2.67 4c0 2.67 2 2.67 2 5.34 0 2.67-2.67 4-4.34 4-2.66 0-4.33-1.34-4.33-4z"
    />
    <template v-else-if="name === 'library'">
      <rect x="2" y="2.67" width="10.67" height="9.34" rx="1" />
      <path d="M2 9.33 8 6l5.33 3.33" />
    </template>
    <template v-else-if="name === 'blueprint'">
      <rect x="2" y="2" width="12" height="12" rx="1" />
      <path d="M2 6h12M6 2v12" />
    </template>
    <template v-else-if="name === 'script'">
      <path d="M2.67 4h10.66M2.67 8h10.66M2.67 12H10" />
    </template>
    <template v-else-if="name === 'localization'">
      <circle cx="8" cy="8" r="6" />
      <path d="M2 8h12M8 2c-3 3-3 9 0 12M8 2c3 3 3 9 0 12" />
    </template>
    <path v-else-if="name === 'review'" d="m3 8 4 4 6-8" />
    <template v-else-if="name === 'publish'">
      <path d="M8 2v10M4 6l4-4 4 4M2.67 14h10.66" />
    </template>
    <path v-else-if="name === 'stats'" d="M2 14v-3M6 14V6M10 14V9M14 14V4" />
    <template v-else>
      <circle cx="8" cy="8" r="2" />
      <path d="M8 1.33v2M8 12.67v2M1.33 8h2M12.67 8h2M3.2 3.2l1.4 1.4M11.4 11.4l1.4 1.4M3.2 12.8l1.4-1.4M11.4 4.6l1.4-1.4" />
    </template>
  </svg>
</template>

<script setup lang="ts">
defineProps<{
  name:
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
}>();
</script>
