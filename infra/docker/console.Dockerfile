# Web 控制台（media-atlas-app）：独立 npm 项目，**不在 pnpm workspace 里**。
# 构建产物是静态资源，由 nginx 托管并把 /api/ 同源反代到控制面 API（无 CORS）。
# build context = 仓库根（compose.yaml 里 context: .）

FROM node:22-alpine AS build
WORKDIR /app

# 先只拷贝清单，命中依赖层缓存；npm ci 严格按 package-lock.json 安装
COPY media-atlas-app/package.json media-atlas-app/package-lock.json ./
RUN npm ci

COPY media-atlas-app/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/docker/console-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
