# Web 控制台（apps/console，pnpm workspace 成员 `@videoforge/console`）。
# 构建产物是静态资源，由 nginx 托管并把 /api/ 同源反代到控制面 API（无 CORS）。
# build context = 仓库根（compose.yaml 里 context: .）

FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable

# 先只拷贝工作区清单，命中依赖层缓存。
# `--filter @videoforge/console...` 的尾随 `...` = 该包 + 它依赖的工作区包（contracts-ts）。
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/console/package.json apps/console/package.json
COPY packages/contracts-ts/package.json packages/contracts-ts/package.json
RUN corepack pnpm install --filter @videoforge/console... --frozen-lockfile

# contracts-ts 是纯类型包（types 指向 src/index.ts，无运行时产物），
# 源码必须在场供 vue-tsc 解析类型；vite 不会把它打进 bundle。
COPY packages/contracts-ts packages/contracts-ts
COPY apps/console apps/console
RUN corepack pnpm --filter @videoforge/console build

FROM nginx:1.27-alpine
COPY infra/docker/console-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/console/dist /usr/share/nginx/html
EXPOSE 80
