# Implementation Plan: 本地安全设置与账号绑定

**Branch**: `[001-secure-local-settings]` | **Date**: 2026-07-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-secure-local-settings/spec.md`

## Summary

补全 M-W10 设置页，提供本地凭据库、LLM/ASR/VLM 配置和抖音/TikTok 账号绑定。凭据库生成随机 master key，用户口令经 Argon2id 派生 wrapping key，再以 AES-256-GCM 包装 master key；每条服务端秘密用 master key 独立认证加密后写入 PostgreSQL。服务重启后默认锁定。遵循既有 ADR：浏览器 Cookie 留在 macOS Keychain、Android 会话留在设备端，控制中心只保存不透明 handle。所有真实外部调用、OAuth、验证码与在线验证仍保持禁用。

## Technical Context

**Language/Version**: Python 3.11、TypeScript 5.5、Vue 3.4
**Primary Dependencies**: FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、argon2-cffi、PyCryptodome、Vue
**Storage**: 本地 PostgreSQL；Desktop Cookie 使用既有 macOS Keychain Broker；Android 会话仅登记设备 handle
**Testing**: pytest（API、持久化、集成与泄露扫描）、Ruff、vue-tsc、Vite build、浏览器 smoke
**Target Platform**: 本机 Docker Compose；控制台与 API 仅绑定 loopback；macOS Desktop 为 Cookie 安全存储端
**Project Type**: Monorepo Web 控制台 + FastAPI 服务 + PostgreSQL 持久化 + Tauri Desktop Broker
**Performance Goals**: 设置摘要本地请求 p95 < 300ms；单次解锁目标 50–500ms；每次秘密写入只做一次 AEAD
**Constraints**: 零真实平台/模型网络调用；零明文落盘/响应/日志/浏览器存储；一进程一解锁状态；乐观锁不静默覆盖
**Scale/Scope**: 单用户本机，3 类 AI Provider，2 个首期平台，可扩展到少量配置与账号

## Constitution Check

*GATE: Phase 0 前通过；Phase 1 设计后复核仍通过。*

- **路线依赖**: M-W10 属 P2，依赖的 VF-002/003/006/007 已存在；本功能不替换 Provider Registry 或 Keychain Broker。
- **单一任务边界**: 本增量仅完成 M-W10“安全设置与账号绑定”，不实现真实 Provider/平台连接。
- **第三方清单优先**: 在代码 import 前登记 `argon2-cffi` 与 `pycryptodome` 的许可证和 L0 隔离级。
- **Provider 规则**: 只保存配置，不新增 Provider 实现；因此不新增 descriptor/健康探测。页面明确“未在线验证/未执行连接测试”。
- **真实账号与付费凭据停止条件**: 只提供本地登记与 Fake/Manual 边界；不索取测试用真实凭据，不触发 OAuth、验证码、风控或付费调用。
- **Secret 边界**: 服务端 Token 加密；Cookie/Android 会话不进入 Web API/DB；响应、错误、日志和任务合同不含秘密。
- **领域纯度**: 不改 `domain`；跨模块只传配置视图和不透明 `credential_ref`。
- **长流程/媒体算法**: 本功能不新增 Temporal 长流程或媒体算法，无需 time-skipping/Golden。
- **本地暴露面**: Compose 发布端口绑定 `127.0.0.1`，控制台同源代理设置 API。

## Project Structure

### Documentation (this feature)

```text
specs/001-secure-local-settings/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── settings-api.yaml
└── tasks.md
```

### Source Code (repository root)

```text
apps/api/
├── pyproject.toml
├── src/videoforge_api/
│   ├── credential_vault.py
│   ├── main.py
│   └── secure_settings.py
└── tests/
    ├── test_credential_vault.py
    ├── test_secure_settings_api.py
    └── test_secure_settings_integration.py

apps/console/src/
├── api/
│   ├── client.ts
│   └── settings.ts
├── components/settings/
│   ├── PlatformAccountsPanel.vue
│   ├── ProviderSettingsPanel.vue
│   └── VaultPanel.vue
└── views/SettingsView.vue

packages/persistence/
├── src/videoforge_persistence/
│   ├── __init__.py
│   ├── settings_store.py
│   └── settings_tables.py
└── tests/test_settings_store.py

migrations/versions/0007_secure_local_settings.py
compose.yaml
third_party_manifest.yaml
uv.lock
```

**Structure Decision**: 复用现有“API gateway + persistence repository + Vue API module”分层。加密只在 API 应用层发生；持久化层只接触密文记录；控制台组件永不接收秘密响应。

## Complexity Tracking

无 Constitution 违例。混合存储不是额外架构，而是落实既有 `AccountBinding.SERVER_ENCRYPTED/DESKTOP/DEVICE` 安全边界。
