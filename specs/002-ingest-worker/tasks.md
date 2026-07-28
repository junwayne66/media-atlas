# Tasks: 可恢复的采集 Worker

**Input**: Design documents from `/specs/002-ingest-worker/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md

**Repository Task ID**: VF-108（以下 Txxx 是该 Task 内的可执行子任务）

## Phase 1: Setup（共享准备）

**Purpose**: 将外部设计决策纳入仓库路线与模块文档，不引入新第三方运行时。

- [X] T001 在 `docs/implementation/53-coder-agent-roadmap.md` 登记 VF-108 及依赖/DoD，并在 `docs/modules/46-ingest-worker.md` 记录外部设计到现有 ADR 的映射
- [X] T002 更新 `connectors/sources/douyin/descriptor.yaml` 的离线 ingest 能力与停止条件，不安装 Playwright

---

## Phase 2: Foundational（阻塞所有用户故事）

**Purpose**: 建立采集合同、只读业务投影、审计和完整 TaskEnvelope/Lease 语义。

**⚠️ CRITICAL**: 本阶段完成前不进入用户故事实现。

- [X] T003 [P] 先在 `packages/contracts-py/tests/test_ingest_contracts.py` 编写 RightsBasis、IngestJob、StageOutcome、SourceProfile、公开元数据与秘密字段拒绝测试
- [X] T004 实现 `packages/contracts-py/src/videoforge_contracts/ingest.py`，向后兼容扩展 `packages/contracts-py/src/videoforge_contracts/source_asset.py` 并更新 `packages/contracts-py/src/videoforge_contracts/__init__.py`
- [X] T005 [P] 在 `migrations/versions/0008_ingest_worker.py` 和 `packages/persistence/src/videoforge_persistence/ingest_tables.py` 创建 ingest_jobs、events、queries、attestations、profiles 只读投影
- [X] T006 [P] 先在 `packages/persistence/tests/test_ingest_repository.py` 编写幂等创建、乐观锁、合法状态转换、append-only event、Rights Gate 和并发去重测试
- [X] T007 实现 `packages/persistence/src/videoforge_persistence/ingest.py` 并更新 `packages/persistence/src/videoforge_persistence/__init__.py`、`migrations/env.py` 和测试清理表
- [X] T008 [P] 先扩充 `packages/persistence/tests/test_lease.py`，覆盖 CANCELLED、旧租约拒绝、完整 TaskEnvelope 持久化和入库前秘密键拒绝
- [X] T009 扩展 `packages/persistence/src/videoforge_persistence/lease.py`、`packages/persistence/src/videoforge_persistence/tables.py`、`apps/api/src/videoforge_api/workers.py` 与 0008 migration，补齐 cancel 和 TaskEnvelope 字段
- [X] T010 [P] 先在 `services/edge-agent/tests/test_agent_flow.py` 编写任务级续租、续租丢失后禁止 complete、execution_policy 路由测试
- [X] T011 实现 `services/edge-agent/src/videoforge_edge_agent/runner.py` 与 `services/edge-agent/src/videoforge_edge_agent/client.py` 的任务级 renew/cancel 语义

**Checkpoint**: 采集业务投影不参与 claim，唯一执行队列仍为 worker_tasks。

---

## Phase 3: User Story 1 - 发现并解析来源内容（Priority: P1）🎯 MVP

**Goal**: 通过离线 Douyin Fixture 或纯 URL 解析异步建立/复用 SourceAsset，明确区分空结果、结构漂移、短链人工处理和永久失败。

**Independent Test**: 使用 board/empty/drift/challenge Fixture 与 50 个规范/短链/无效输入，所有请求最终得到来源、明确人工处置或稳定错误，重复输入只产生一条事实。

### Tests for User Story 1

- [X] T012 [P] [US1] 在 `packages/provider-sdk/tests/test_network_guard.py` 编写 HTTPS、userinfo、混淆 host、私网 DNS 和逐跳重定向 fail-closed 测试
- [X] T013 [P] [US1] 在 `services/edge-agent/tests/test_ingest_provider.py` 编写 descriptor、fixture discover、empty/drift/challenge、resolve、health 和零网络测试
- [X] T014 [P] [US1] 在 `packages/workflows/tests/test_ingest_workflow.py` 编写 discover/resolve happy path、空结果与 scoped idempotency 的 Temporal time-skipping 测试
- [X] T015 [P] [US1] 在 `apps/api/tests/test_ingest_api.py` 编写 discovery/resolve 202、幂等 header、查询与输入错误契约测试

### Implementation for User Story 1

- [X] T016 [US1] 实现 `packages/provider-sdk/src/videoforge_provider_sdk/network_guard.py` 并从 `packages/provider-sdk/src/videoforge_provider_sdk/__init__.py` 导出
- [X] T017 [US1] 实现 `services/edge-agent/src/videoforge_edge_agent/ingest_provider.py`，在 `services/edge-agent/src/videoforge_edge_agent/main.py` 注册离线 Douyin Provider
- [X] T018 [US1] 实现 `packages/workflows/src/videoforge_workflows/ingest.py` 的 discover/resolve 编排并更新 `packages/workflows/src/videoforge_workflows/__init__.py`
- [X] T019 [US1] 实现 `apps/temporal-worker/src/videoforge_temporal_worker/ingest_activities.py` 的状态投影和 SourceAsset 幂等持久化，并在 `apps/temporal-worker/src/videoforge_temporal_worker/main.py` 注册
- [X] T020 [US1] 实现 `apps/api/src/videoforge_api/ingest.py` 的 discovery/resolve/start/get/events 服务与路由，并在 `apps/api/src/videoforge_api/main.py` 装配
- [X] T021 [US1] 在 `apps/api/tests/test_ingest_integration.py` 完成真实 PostgreSQL 的并发来源去重、空结果、结构漂移和 canary 泄露扫描

**Checkpoint**: US1 可在不配置账号、不触网时独立运行。

---

## Phase 4: User Story 2 - 经授权获取原始媒体（Priority: P2）

**Goal**: Rights Gate 后由 Edge Worker 上传合成媒体，服务端验证并创建不可变 Artifact，重复获取复用、force 创建新版本。

**Independent Test**: UNKNOWN 零对象；允许依据的合成媒体生成 SHA/size/MIME/容器/时长/尺寸完整的 Artifact，重复和强制获取符合版本语义。

### Tests for User Story 2

- [X] T022 [P] [US2] 在 `packages/media-core/tests/test_artifact_store.py` 增加 staging inspect、类型/大小/容器签名和孤儿清理边界测试
- [X] T023 [P] [US2] 在 `services/edge-agent/tests/test_ingest_provider.py` 增加合成媒体 golden 与 staging 上传测试
- [X] T024 [P] [US2] 在 `apps/api/tests/test_ingest_integration.py` 增加 UNKNOWN 零对象、授权成功、重复复用、force 新版本和事务失败孤儿证据测试
- [X] T025 [P] [US2] 在 `packages/workflows/tests/test_ingest_workflow.py` 增加 Rights Gate 先于 dispatch 和 acquire 编排 time-skipping 测试

### Implementation for User Story 2

- [X] T026 [US2] 扩展 `packages/media-core/src/videoforge_media_core/artifact_store.py` 的 staging 检查与采集命名空间安全清理能力
- [X] T027 [US2] 实现 `apps/api/src/videoforge_api/artifact_uploads.py` 的 job-scoped stage/commit API，并更新 `services/edge-agent/src/videoforge_edge_agent/client.py`
- [X] T028 [US2] 在 `services/edge-agent/src/videoforge_edge_agent/ingest_provider.py` 实现离线合成媒体获取、完整性声明和短时上传
- [X] T029 [US2] 在 `apps/api/src/videoforge_api/ingest.py`、`apps/temporal-worker/src/videoforge_temporal_worker/ingest_activities.py` 实现 attestation、获取任务、Artifact/SourceAsset 关联与重复策略

**Checkpoint**: US2 可用 MinIO + 合成媒体独立验收，真实平台下载仍关闭。

---

## Phase 5: User Story 3 - 处理挑战并人工恢复（Priority: P3）

**Goal**: 挑战/登录失效不快速重试，任务进入 NEED_HUMAN，只有显式恢复可重新派发，取消保持终态。

**Independent Test**: challenge Fixture 一次派发后长期等待，resume generation 变化后重新执行；非法恢复 409；取消后迟到 Worker 无副作用。

### Tests for User Story 3

- [X] T030 [P] [US3] 在 `packages/workflows/tests/test_ingest_workflow.py` 增加挑战零自动重试、合法/非法 resume、cancel 竞态和 replay 恢复 time-skipping 测试
- [X] T031 [P] [US3] 在 `apps/api/tests/test_ingest_api.py` 增加 resume/cancel 202/409、脱敏调试上下文和终态保护测试

### Implementation for User Story 3

- [X] T032 [US3] 在 `packages/workflows/src/videoforge_workflows/ingest.py` 实现 WAITING_FOR_HUMAN、resume/cancel update、generation idempotency key 和迟到结果抑制
- [X] T033 [US3] 在 `apps/api/src/videoforge_api/ingest.py` 与 `apps/temporal-worker/src/videoforge_temporal_worker/ingest_activities.py` 实现 resume/cancel 和不可变审计

**Checkpoint**: US3 可在完全离线 challenge Fixture 上独立验收。

---

## Phase 6: User Story 4 - 可恢复且可审计运行（Priority: P4）

**Goal**: 并发 Worker、租约过期、暂时错误和永久错误均有确定终态、完整事件与健康诊断。

**Independent Test**: 两个 Worker 并发领取 100 个任务无重复；租约过期可恢复；RATE_LIMITED 按 Temporal Timer 有界退避；失败事件稳定可查。

### Tests for User Story 4

- [X] T034 [P] [US4] 在 `packages/workflows/tests/test_ingest_workflow.py` 增加 RATE_LIMITED timer 退避、attempt key 和永久错误不重试测试
- [X] T035 [P] [US4] 在 `packages/persistence/tests/test_lease.py` 增加两个 Worker/100 任务并发、过期重领和 stale complete 压力测试
- [X] T036 [P] [US4] 在 `apps/api/tests/test_ingest_integration.py` 增加事件顺序、陈旧租约、错误码和结构化健康检查测试

### Implementation for User Story 4

- [X] T037 [US4] 在 `packages/workflows/src/videoforge_workflows/ingest.py` 实现 typed retryable outcome、Temporal Timer 与有界 attempt
- [X] T038 [US4] 在 `apps/api/src/videoforge_api/ingest.py` 增加任务积压、陈旧租约、解析器错误和挑战计数的 readiness 诊断

**Checkpoint**: 四个用户故事均可独立查询、恢复和审计。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 本地部署、文档、供应链和全量验证。

- [X] T039 [P] 更新 `infra/docker/worker.Dockerfile` 与 `compose.yaml`，加入 workflow-worker/edge-agent、内部 S3 配置和健康依赖
- [X] T040 [P] 在 `apps/api/src/videoforge_api/secure_settings.py` 收紧 Desktop/Device opaque handle，禁止路径语义
- [X] T041 更新 `packages/contracts-py/tests/samples.py`、`schemas/source-asset.schema.json` 和合同 fixture，验证向后兼容 round-trip
- [X] T042 运行 `specs/002-ingest-worker/quickstart.md` 的定向测试、全仓 lint/typecheck/build、Compose 启动与健康验收并记录结果

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup 无依赖。
- Foundational 依赖 Setup，阻塞全部用户故事。
- US1 依赖 Foundational；是 MVP。
- US2 依赖 Foundational 与 US1 的 SourceAsset/Workflow 基线。
- US3 依赖 US1 的 Workflow/API，但不依赖 US2 的媒体上传。
- US4 依赖 US1/US3 的状态机；压力测试可与 US2 并行准备。
- Polish 依赖目标用户故事完成。

### User Story Dependencies

```text
Foundation -> US1 -> US2
                  -> US3 -> US4
Foundation ----------------> US4 lease tests
```

### Parallel Opportunities

- T003/T005/T006/T008/T010 可在不同文件中并行准备测试与 schema。
- US1 的 T012–T015 可并行先写失败测试。
- US2 的 T022–T025 可并行。
- US3 的 Workflow 与 API 测试可并行。
- US4 的 workflow、lease、API 集成测试可并行。

---

## Implementation Strategy

### MVP First

1. 完成 T001–T011。
2. 完成 T012–T021。
3. 验证离线 discovery/resolve、幂等来源和零真实网络。

### Incremental Delivery

1. US1：离线发现/解析。
2. US2：Rights Gate + 合成媒体 Artifact。
3. US3：挑战人工恢复/取消。
4. US4：重试、并发、健康与审计。
5. Polish：Compose 全栈启动和全仓验证。

## Format Validation

全部 42 个任务均使用 `- [ ] Txxx [P?] [US?] 描述 + 精确文件路径` 格式；用户故事阶段均
带 `[USn]`，Setup/Foundation/Polish 不带 Story 标签。
