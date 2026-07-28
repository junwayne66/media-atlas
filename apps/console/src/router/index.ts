import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    redirect: "/dashboard",
  },
  {
    path: "/dashboard",
    name: "Dashboard",
    component: () => import("@/views/DashboardView.vue"),
    meta: { title: "项目工作台", nav: "项目" },
  },
  {
    path: "/hotspots",
    name: "Hotspots",
    component: () => import("@/views/HotspotsView.vue"),
    meta: { title: "热点池", nav: "热点池" },
  },
  {
    path: "/library",
    name: "Library",
    component: () => import("@/views/LibraryView.vue"),
    meta: { title: "素材库", nav: "素材库" },
  },
  {
    path: "/blueprint",
    name: "Blueprint",
    component: () => import("@/views/BlueprintView.vue"),
    meta: { title: "创作编辑", nav: "创作编辑" },
  },
  {
    path: "/script-editor",
    name: "ScriptEditor",
    component: () => import("@/views/ScriptEditorView.vue"),
    meta: { title: "脚本编辑", nav: "脚本编辑" },
  },
  {
    path: "/localization",
    name: "Localization",
    component: () => import("@/views/LocalizationView.vue"),
    meta: { title: "本地化", nav: "本地化" },
  },
  {
    path: "/review",
    name: "Review",
    component: () => import("@/views/ReviewView.vue"),
    meta: { title: "审核中心", nav: "审核" },
  },
  {
    path: "/publish",
    name: "Publish",
    component: () => import("@/views/PublishView.vue"),
    meta: { title: "发布", nav: "发布" },
  },
  {
    path: "/stats",
    name: "Stats",
    component: () => import("@/views/StatsView.vue"),
    meta: { title: "效果看板", nav: "效果" },
  },
  {
    path: "/settings",
    name: "Settings",
    component: () => import("@/views/SettingsView.vue"),
    meta: { title: "系统与设置", nav: "设置" },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
