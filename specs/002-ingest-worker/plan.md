# Implementation Plan: 可恢复的采集 Worker

**Branch**: `main`（工作区已有未提交改动，本任务不擅自切分支） | **Date**: 2026-07-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-ingest-worker/spec.md`

## Summary

在现有 VideoForge 架构中加入抖音采集控制面与本地 Edge Worker 能力，覆盖离线发现、
URL 解析、授权后合成媒体获取、任务查询、取消、挑战转人工和显式恢复。外部设计中的
`crawl_jobs` 不作为第二套队列引入：Temporal 负责长流程与人工等待，现有
`worker_tasks`/Task Lease 负责独占领取、续租、过期恢复和幂等提交；新增 `ingest_jobs`
只是业务查询投影，`ingest_job_events` 是不可变审计日志。

标准化内容继续使用现有 `SourceAsset` 聚合，并以向后兼容的可选字段补充公开元数据、
RightsBasis 与 Artifact 引用；真实媒体继续落现有 Artifact Store/MinIO。Edge Agent
注册一个隔离的 Douyin 离线 Provider，复用现有 Douyin connector、URL resolver、
错误映射和 Fixture。真实 Playwright/Profile、平台 Cookie、线上抓取与下载均不在本次
启用范围内，遇到挑战或未配置状态统一进入人工等待。

## Technical Context

**Language/Version**: Python 3.11+；Vue 3/TypeScript（复用现有控制台）

**Primary Dependencies**: FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、Temporal Python SDK、boto3、httpx；现有 `videoforge-provider-sdk`、Douyin connector、media-core

**Storage**: PostgreSQL（业务投影、审计、SourceAsset、Artifact 元数据）；MinIO/S3（不可变媒体和调试 Artifact）

**Testing**: pytest、pytest-asyncio、Temporal time-skipping、Testcontainers PostgreSQL/MinIO、离线 JSON/HTML/合成媒体 Fixture

**Target Platform**: macOS 本地开发与 Linux 容器；Edge Worker 仅发起出站连接

**Project Type**: Python monorepo中的 Web API + Temporal Worker + Edge Agent + 平台 connector

**Performance Goals**: 两个 Worker 并发处理 100 个离线任务时重复领取为零；搜索受 `max_items`、最大轮次、空闲轮次和总预算约束；单媒体默认上限 500 MiB

**Constraints**: 默认零真实平台网络；UNKNOWN 权利依据零对象写入；任务信封、数据库、事件和日志零明文凭据；只允许 Douyin 公共 HTTPS 主机；原始事实与 Artifact 不可变；不执行任意 shell 字符串

**Scale/Scope**: 本地单机、1–5 个账号、每天不超过 20 条视频；本 Task 为 `VF-108 Recoverable Ingest Worker`

## Constitution Check

*GATE: Phase 0 前通过；Phase 1 设计后复核通过。仓库 constitution 文件仍是模板，
因此以根 `AGENTS.md`、`CLAUDE.md` 和现有 ADR 为强制规则。*

- **依赖顺序**：VF-108 依赖已完成的 VF-004/005/006/007/101/102/105/106/107，
  位于 P1 Exit 的补强位置。通过。
- **单 Task ID**：代码、迁移、契约、测试、Compose 和文档均归属 VF-108；不提交当前
  工作区中其他未提交功能。通过。
- **第三方先登记**：本设计不新增 Playwright 或新镜像；只复用清单已有依赖和镜像。
  后续真实浏览器适配器必须先更新 manifest。通过。
- **Provider 完整性**：Douyin 离线 Provider 复用 descriptor，并补齐 source.resolve/
  source.acquire 能力、契约测试、稳定错误映射和健康检查。通过。
- **Temporal 测试**：IngestWorkflow 增加 time-skipping，覆盖挑战等待、resume、cancel
  与幂等派发。通过。
- **媒体 Fixture/Golden**：授权获取使用合成媒体，校验容器签名、字节数、SHA-256 和
  时长/尺寸元数据，不只比较文件 hash。通过。
- **Secret/真实账号**：测试只用 canary 与不透明 profile handle；不使用真实 Cookie、
  Token、验证码或付费账号。通过。
- **边界**：domain 不依赖框架；跨模块只传 ID/结构化合同；不引入 shell 字符串。通过。
- **停止条件**：真实 Douyin/Playwright/Profile 仍为 Manual/Unconfigured，不扩大范围。
  通过。

## Project Structure

### Documentation (this feature)

```text
specs/002-ingest-worker/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/ingest-api.yaml
└── tasks.md
```

### Source Code (repository root)

```text
apps/api/
├── src/videoforge_api/
│   ├── ingest.py
│   └── artifact_uploads.py
└── tests/
    ├── test_ingest_api.py
    └── test_ingest_integration.py

apps/temporal-worker/
├── src/videoforge_temporal_worker/ingest_activities.py
└── tests/test_ingest_activities.py

packages/contracts-py/src/videoforge_contracts/ingest.py
packages/persistence/src/videoforge_persistence/{ingest.py,ingest_tables.py}
packages/workflows/src/videoforge_workflows/ingest.py
packages/provider-sdk/src/videoforge_provider_sdk/network_guard.py
services/edge-agent/src/videoforge_edge_agent/ingest_provider.py
connectors/sources/douyin/{descriptor.yaml,fixtures/,tests/}
migrations/versions/0008_ingest_worker.py
docs/modules/46-ingest-worker.md
```

**Structure Decision**: 保持现有模块化单体和 workspace 包边界。业务合同在
`contracts-py`，持久化在 `persistence`，纯 Workflow 在 `workflows`，带数据库和对象存储
I/O 的 Activity 在 `temporal-worker`，平台实现留在 Douyin connector/Edge Agent，API 只做
编排和权限 gate。

## Complexity Tracking

无 constitution 违规。`ingest_jobs` 是 Temporal/Task Lease 的只读业务投影，不具备 claim
SQL，不构成第二套任务队列。
