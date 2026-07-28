# Tasks: 本地安全设置与账号绑定

**Input**: Design documents from `/specs/001-secure-local-settings/`

**Task boundary**: M-W10 安全设置与账号绑定；不实现真实 Provider/平台联网。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 先登记依赖并收敛本地暴露面。

- [X] T001 在 `third_party_manifest.yaml` 登记 argon2-cffi 与 PyCryptodome 的许可证、用途和 L0 隔离级
- [X] T002 在 `apps/api/pyproject.toml` 增加直接加密依赖并更新 `uv.lock`
- [X] T003 [P] 将 `compose.yaml` 的宿主机发布端口全部限制到 127.0.0.1

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 为所有设置故事建立密文持久化、事务和脱敏错误基础。

- [X] T004 在 `migrations/versions/0007_secure_local_settings.py` 和 `packages/persistence/src/videoforge_persistence/settings_tables.py` 建立 vault、credential、provider、account 表与约束
- [X] T005 在 `packages/persistence/src/videoforge_persistence/settings_store.py` 实现只处理密文/locator 的仓储、CAS 更新与原子删除
- [X] T006 [P] 在 `packages/persistence/src/videoforge_persistence/__init__.py`、`migrations/env.py` 和测试 fixtures 中加载/导出新表与仓储
- [X] T007 在 `apps/api/src/videoforge_api/secure_settings.py` 建立请求/响应模型、敏感键拒绝、脱敏校验错误和稳定错误映射骨架
- [X] T008 [P] 在 `apps/console/src/api/client.ts` 增加 PUT/DELETE，并保持 ApiError 的 409 语义

**Checkpoint**: 数据结构、事务边界和错误脱敏可供各故事复用。

---

## Phase 3: User Story 1 - 初始化并解锁本地凭据库 (Priority: P1) 🎯 MVP

**Goal**: 保险库可初始化、解锁、锁定，重启后默认锁定，数据库无口令/明文主密钥。

**Independent Test**: 用合成口令初始化，锁定后秘密操作拒绝，正确/错误解锁可区分，重建 gateway 后状态为 LOCKED。

### Tests for User Story 1

- [X] T009 [P] [US1] 在 `apps/api/tests/test_credential_vault.py` 添加 KDF/envelope AEAD、篡改、随机 nonce、锁定和并发测试
- [X] T010 [P] [US1] 在 `packages/persistence/tests/test_settings_store.py` 添加 vault singleton、rollback 与密文 roundtrip 测试
- [X] T011 [P] [US1] 在 `apps/api/tests/test_secure_settings_api.py` 添加 vault 端点状态码与 422 零回显契约测试

### Implementation for User Story 1

- [X] T012 [US1] 在 `apps/api/src/videoforge_api/credential_vault.py` 实现 Argon2id KEK、wrapped master DEK、AES-GCM、进程锁定态、并发容量限制和尽力覆零
- [X] T013 [US1] 在 `apps/api/src/videoforge_api/secure_settings.py` 实现 vault initialize/unlock/lock/status gateway 与路由
- [X] T014 [US1] 在 `apps/api/src/videoforge_api/main.py` 注册长期 settings gateway、路由和 no-store 响应策略
- [X] T015 [P] [US1] 在 `apps/console/src/api/settings.ts` 实现 vault/settings snapshot 类型与 API 调用
- [X] T016 [US1] 在 `apps/console/src/components/settings/VaultPanel.vue` 实现三态表单、局部秘密生命周期和无回显反馈

**Checkpoint**: 用户可安全初始化/锁定/解锁本地凭据库。

---

## Phase 4: User Story 2 - 配置 AI Providers (Priority: P1)

**Goal**: LLM/ASR/VLM 可保存非敏感配置，明确 KEEP/REPLACE/CLEAR 凭据并防止并发覆盖。

**Independent Test**: 三类配置均完成创建、刷新、非敏感更新、凭据替换/清除、锁定拒绝和 stale version 409。

### Tests for User Story 2

- [X] T017 [P] [US2] 在 `packages/persistence/tests/test_settings_store.py` 添加 Provider CRUD、唯一性、CAS 与 owner/credential 原子性测试
- [X] T018 [P] [US2] 在 `apps/api/tests/test_secure_settings_api.py` 添加 Provider 契约、锁定、409 和响应不含 credential_ref/secret 测试

### Implementation for User Story 2

- [X] T019 [US2] 在 `apps/api/src/videoforge_api/secure_settings.py` 实现 Provider upsert/delete、KEEP/REPLACE/CLEAR 和 readiness 视图
- [X] T020 [P] [US2] 在 `apps/console/src/api/settings.ts` 实现 Provider CRUD 类型和调用
- [X] T021 [US2] 在 `apps/console/src/components/settings/ProviderSettingsPanel.vue` 实现 LLM/ASR/VLM 响应式卡片、独立秘密表单与冲突重载
- [X] T022 [US2] 在 `apps/console/src/views/SettingsView.vue` 接入保险库与 Provider tab，同时保留 Worker/System 功能

**Checkpoint**: 三类 Provider 设置可独立持久化且明文不回显。

---

## Phase 5: User Story 3 - 保存真实平台账号绑定材料 (Priority: P2)

**Goal**: 抖音/TikTok 可登记 SERVER_ENCRYPTED、DESKTOP、DEVICE 绑定，始终 UNVERIFIED 且零真实网络。

**Independent Test**: 官方 Token 加密保存；浏览器/设备只接受 handle；删除绑定使本地引用失效且无服务端孤儿密文。

### Tests for User Story 3

- [X] T023 [P] [US3] 在 `packages/persistence/tests/test_settings_store.py` 添加账号唯一性、CAS、locator 与删除原子性测试
- [X] T024 [P] [US3] 在 `apps/api/tests/test_secure_settings_api.py` 添加账号组合校验、明文 Cookie/设备会话结构性拒绝及 UNVERIFIED 测试

### Implementation for User Story 3

- [X] T025 [US3] 在 `apps/api/src/videoforge_api/secure_settings.py` 实现账号 create/update/delete、绑定位置约束和不透明 credential locator
- [X] T026 [P] [US3] 在 `apps/console/src/api/settings.ts` 实现账号绑定 CRUD 类型和调用
- [X] T027 [US3] 在 `apps/console/src/components/settings/PlatformAccountsPanel.vue` 实现账号表单、绑定位置引导、删除确认与 UNVERIFIED 状态
- [X] T028 [US3] 在 `apps/console/src/views/SettingsView.vue` 增加独立平台账号 tab，禁止真实连接/验证动作

**Checkpoint**: 账号绑定材料按正确安全位置保存，控制台只见元数据与配置状态。

---

## Phase 6: User Story 4 - 安全管理和诊断配置 (Priority: P3)

**Goal**: 页面完整区分未初始化、锁定、缺凭据、禁用、冲突、未验证和服务错误。

**Independent Test**: 所有状态均有非敏感文案；键盘/窄屏可用；合成 canary 在 DB/API/log/browser storage 中出现次数为 0。

### Tests for User Story 4

- [X] T029 [P] [US4] 在 `apps/api/tests/test_secure_settings_integration.py` 添加真实数据库迁移、重启锁定、事务竞态和 raw-row/API/log canary 扫描

### Implementation for User Story 4

- [X] T030 [US4] 在 `apps/console/src/components/settings/*.vue` 与 `apps/console/src/views/SettingsView.vue` 完成 ARIA tabs、label、aria-live、响应式布局和固定脱敏错误文案
- [X] T031 [US4] 在 `infra/docker/console-nginx.conf`、`apps/desktop/src-tauri/tauri.conf.json` 和设置 API 增加 CSP、no-referrer、nosniff、frame-ancestors 与 no-store 安全头

**Checkpoint**: 设置页的安全与诊断状态完整且可验证。

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T032 [P] 更新 `docs/modules/45-web-ui.md` 的 M-W10 端点状态和安全边界
- [X] T033 执行 `uv run ruff check .`、设置专项 pytest、全量 pytest、console typecheck/build 与 `make smoke`
- [X] T034 按 `specs/001-secure-local-settings/quickstart.md` 完成浏览器验收，检查 URL/DOM、代码存储路径、API 响应、network/console 零明文及窄屏/键盘行为

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → US1。
- US2 依赖 US1 的 vault；US3 依赖 US1 的 vault 和 Phase 2 locator；US4 依赖 US1–US3 的状态面。
- T009/T010/T011 可并行；T017/T018 可并行；T023/T024 可并行。
- 前端 API 模块可在对应后端契约稳定后与后端测试并行。

## Parallel Examples

```text
US1: T009 crypto tests || T010 persistence tests || T011 API contract tests
US2: T017 persistence tests || T018 API contract tests
US3: T023 persistence tests || T024 API contract tests
```

## Implementation Strategy

1. **MVP**: Setup + Foundation + US1，先证明本地保险库零明文与重启锁定。
2. **Provider increment**: 完成 US2 的三类配置与并发冲突。
3. **Account increment**: 完成 US3 的混合存储，不越过真实联网停止条件。
4. **Hardening**: 完成 US4、全量回归和浏览器泄露检查。

## Format Validation

全部 34 项均使用 `- [ ] TNNN [P?] [US?] 描述 + 精确文件路径` 格式。
