import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";

// 开发期通过 /api 前缀反代到控制平面 API，避免浏览器跨域（与 apps/web 写法一致）；
// 容器内由 nginx 做同源反代（infra/docker/console-nginx.conf），不走这里。
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  server: {
    port: 3000,
    host: true,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  // vue-router 用 history 模式：base 必须是绝对根路径，
  // 子路由刷新由 nginx `try_files ... /index.html` 兜底。
  base: "/",
});
