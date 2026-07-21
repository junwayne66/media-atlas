# VideoForge

热点驱动、AI 辅助、人工可控、跨平台发布的多语言短视频再创作系统。完整设计文档见 [docs/](docs/README.md)，当前实现进度对应 [docs/implementation/53-coder-agent-roadmap.md](docs/implementation/53-coder-agent-roadmap.md) 的 **VF-001（Monorepo 地基）**。

## 环境要求

- macOS（首期验证环境）或 Linux
- [uv](https://docs.astral.sh/uv/)（Python 3.11 工作区）
- Node.js ≥ 20 + [pnpm](https://pnpm.io/)（可用 `corepack enable` 启用）
- Docker Desktop / Docker Engine（Compose v2）

## 快速开始

```bash
uv sync            # 安装 Python 工作区依赖
pnpm install       # 安装 Web 依赖
make dev           # 构建并启动全套本地栈
make smoke         # 健康检查
```

启动后的入口：

| 服务 | 地址 |
|---|---|
| 控制平面 API | http://localhost:8000/healthz |
| Web 管理台 | http://localhost:5173 |
| Temporal UI | http://localhost:8233 |
| MinIO Console | http://localhost:9001 |

端口冲突时 `cp .env.example .env` 后修改对应端口。

## 常用命令

| 命令 | 作用 |
|---|---|
| `make dev` | 构建并启动全部容器（API、Web、Postgres、Redis、MinIO、Temporal） |
| `make dev-infra` | 只启动基础设施容器，配合 `make api` / `make web` 本机热重载 |
| `make lint` / `make fmt` | ruff + vue-tsc 检查 / 自动格式化 |
| `make test` | pytest + vitest |
| `make ci` | lint + test（CI 同款入口） |
| `make down` | 停止容器（保留数据卷） |

## 仓库结构

```text
apps/api        FastAPI 控制平面（模块化单体）
apps/web        Vue 3 管理台
infra/docker    容器构建文件
docs/           设计文档（实现的唯一依据）
schemas/…       后续任务按 docs/implementation/52-repo-structure.md 增量补齐
```

## 参与开发

- 按 [AGENTS.md](AGENTS.md) 与 [CLAUDE.md](CLAUDE.md) 的规则执行任务。
- 任务顺序、依赖与验收标准以 [docs/implementation/53-coder-agent-roadmap.md](docs/implementation/53-coder-agent-roadmap.md) 为准。
- 新增外部依赖先登记 [third_party_manifest.yaml](third_party_manifest.yaml)。
