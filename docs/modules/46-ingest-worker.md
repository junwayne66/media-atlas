# 采集 Worker

Task：VF-108。外部设计来源：
`/Users/btkj_wayne/Desktop/recipe-studio-ingest-docs`。

## 1. 集成结论

外部文档描述的是独立 Recipe Studio 服务；本仓库是 VideoForge 模块化单体。集成时保留
其“发现、解析、授权获取、人工恢复、不可变审计、对象 staging、SSRF 防护”语义，但以下
现有架构是最终真值：

| 外部概念 | VideoForge 映射 |
|---|---|
| ContentItem | `SourceAsset` + 不可变来源观测 |
| MediaAsset | `Artifact` + SourceAsset 关联 |
| crawl_jobs | Temporal Workflow + `worker_tasks` Task Lease |
| crawl_job_events | Ingest 只读投影/append-only 审计 |
| PostgreSQL SKIP LOCKED Worker | 现有 `WorkerTaskRepository.claim()` |
| MinIO object | 现有 `ArtifactStore.stage_upload()/commit()` |
| 浏览器 Profile path | Desktop Broker 的不透明、短期 handle |

`ingest_jobs`（如存在）只能是 API 查询投影，禁止包含 claim/run-after SQL 或驱动执行。

## 2. 执行链

```text
API Rights/Input Gate
  -> IngestWorkflow
  -> dispatch_to_worker Activity
  -> worker_tasks Lease
  -> Edge Agent offline Douyin Provider
  -> typed StageOutcome
  -> control-plane persistence Activity
  -> SourceAsset / Artifact / audit event
```

Temporal 管理 stage retry timer、人工等待、resume generation 和 cancel；WorkerTask 只表示一个
阶段的一次独占执行。平台限流返回 retryable outcome，由 Workflow 定时重派；登录失效、验证码、
风控和未配置返回 human outcome，禁止 `/fail` 快速循环。

## 3. 权利与媒体

- 来源默认 `RightsBasis.UNKNOWN`，只允许公开 metadata。
- OWNED、LICENSED、USER_PROVIDED、INTERNAL_APPROVED 才能创建获取任务。
- Rights Gate 在申请预签名上传 URL之前执行，UNKNOWN 保证零对象。
- Worker 只在运行时申请短时 staging URL，URL 不进入任务参数、事件或日志。
- 服务端重新计算 SHA/size，校验 MIME、容器签名和媒体 probe 后才创建不可变 Artifact。
- 同来源同 hash 复用；强制获取且 hash 不同则追加新 Artifact，旧版本不覆盖。

## 4. Profile 与浏览器边界

首版不安装 Playwright、不访问真实抖音、不读取 Cookie。`credential_handle` 只作为 Desktop
Profile Broker 的字典键，绝不能解释为路径。当前 Tauri Keychain 没有供独立 edge-agent
解封的 IPC，因此真实浏览器接入的前置任务是实现“Sidecar 可用、WebView 不可用”的短期
scope handle broker；在此之前 Provider health 必须诚实返回 UNCONFIGURED 或 Fixture-only。

真实浏览器接入前还必须：

1. 先登记 Playwright 与固定 Chromium revision 的许可证、校验和和隔离等级；
2. 获得真实测试账号与显式授权；
3. 对首跳、每次 redirect、Document/XHR/Fetch/WebSocket 做 allowlist + 公网地址校验；
4. 挑战立即停到人工，不自动登录、解验证码、刷新、换账号或换下载器绕过。

## 5. 安全与可观测性

- TaskEnvelope、业务表和事件结构上拒绝 Cookie/Authorization/token/password 等敏感键。
- URL 必须 HTTPS、无 userinfo、无混淆 host，并在每跳 DNS 后拒绝 loopback/private/link-local/
  multicast/reserved 地址。
- 调试信息采用 allowlist，只保存当前规范 URL、页面标题、Profile ID、时间、原因码和受限
  Artifact ID；不保存 headers、DOM、signed media URL 或 profile path。
- 日志至少关联 request/job/workflow/task/worker/platform/profile/source/error_code。
- `/readyz` 诊断 DB、对象存储、任务积压、陈旧租约、解析器错误和 challenge 增长。

## 6. 测试边界

自动化只使用仓库内脱敏 JSON/HTML Fixture 和合成媒体。Temporal time-skipping 覆盖
happy path、限流退避、challenge 零自动重试、resume、cancel、replay 与 Rights Gate。
媒体 Golden 比较帧/音频/时长/尺寸或等价技术指标，不只比较文件 hash。真实平台 smoke
默认关闭，不能进入 CI。

## 7. 2026-07-27 本地验收记录

- `pytest -q`：1765 passed；覆盖合同、PostgreSQL/MinIO 集成、Temporal time-skipping、
  并发租约、Rights Gate、合成媒体 Golden、秘密 canary 与设置凭据库。
- `ruff check .`、Console `vue-tsc --noEmit`、Vite production build、`git diff --check`
  均通过。
- Compose 已启动 PostgreSQL、Redis、MinIO、Temporal、Temporal UI、API、Workflow Worker、
  Edge Agent 和 Console；API、数据库与对象存储 readiness 均为 ready。
- 本地离线 Douyin discovery 实跑成功并持久化 2 条 SourceAsset；随后对其中一条执行
  OWNED attestation 与 synthetic MP4 acquisition，服务端验证 SHA-256、1546 bytes、
  `video/mp4`、H.264、16×16、1 秒并创建不可变 Artifact。
- 浏览器验收确认新 UI、API 在线状态、LLM/ASR/VLM、本地凭据库与 Douyin/TikTok
  账号绑定界面可用，控制台无错误。真实 Provider、账号登录、验证码和平台网络仍关闭。
