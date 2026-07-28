# Research: 可恢复的采集 Worker

## 决策 1：任务编排复用 Temporal + Task Lease

**Decision**：Temporal `IngestWorkflow` 管理长流程、人工等待与取消；现有
`WorkerTaskRepository` 继续作为唯一执行队列，Edge Agent 通过 claim/renew/complete
协议运行。新增 `ingest_jobs` 只保存 API 可查询的业务状态，所有变更追加
`ingest_job_events`。

**Rationale**：仓库 ADR 已明确 Temporal 是长流程真值、Task Lease 是边缘执行协议。
外部设计的 `crawl_jobs ... FOR UPDATE SKIP LOCKED` 与现有 `worker_tasks` 的语义重复，
照搬会产生双重重试、双重租约和不一致终态。

**Alternatives considered**：

- 新建 `crawl_jobs` 队列：拒绝，违反核心 ADR。
- API 同步完成采集：拒绝，无法支持崩溃恢复、人工等待和租约。
- 只用 Temporal Activity 直连平台：拒绝，平台/Profile 必须留在隔离 Edge Worker。

## 决策 2：SourceAsset 是标准化来源聚合

**Decision**：不新建重复的 `content_items` 聚合；向 `SourceAsset` 增加向后兼容字段：
公开元数据、`rights_basis`、发现/观察时间、`artifact_ids` 和 rights attestation 引用。
原始观测仍用不可变 snapshot/event 保存，SourceAsset 只保存当前业务视图。

**Rationale**：现有 SourceAsset 已有 `(platform, content_id)` 与 input digest 的并发幂等
约束、项目反向关联和处置状态。新建 content_items 会让分析链与采集链持有两套来源 ID。

## 决策 3：Rights Gate 在任何 staging 之前执行

**Decision**：媒体获取 API 只接受 OWNED、LICENSED、USER_PROVIDED、
INTERNAL_APPROVED；同事务写不可变 attestation 与 ingest job。UNKNOWN 返回 409，
不会创建上传凭据或对象。

## 决策 4：首版不引入 Playwright

**Decision**：首版 Douyin Provider 只回放本仓库 Fixture、纯解析规范 URL、上传合成媒体；
`profile_handle` 只是不透明引用。挑战 Fixture返回 NEED_HUMAN。真实浏览器 fetcher 保持
Unconfigured/Manual，且 handle 绝不解释为文件路径。

**Rationale**：真实 Playwright 路径需要浏览器二进制、持久 Profile、账号、Cookie、
验证码/风控处理和 Desktop Broker IPC，属于 AGENTS.md 停止条件。

## 决策 5：Worker 通过短时 staging API 上传，不持久化预签名 URL

**Decision**：TaskEnvelope 只携带 job/source/profile ID。Worker 在执行时向控制面申请
短时上传 URL，直接 PUT 到 MinIO，再以 upload id + 声明的 SHA/size/MIME 提交。API
服务端重新流式校验并创建不可变 Artifact；预签名 URL 不进入任务表、事件或日志。

## 决策 6：SSRF 防线独立且每跳验证

**Decision**：增加 provider-sdk 的纯 URL target validator，要求 HTTPS、无 userinfo、
host 在 Douyin allowlist、DNS 结果全部为公共地址；实际网络 fetcher（未来）必须在首跳与
每次重定向调用。测试注入 resolver，不触网。

## 决策 7：错误分为 transient / human / permanent

**Decision**：沿用 connector 与 acquisition 的稳定错误码。CHALLENGE_REQUIRED、
AUTH_REQUIRED、UNCONFIGURED 进入 NEED_HUMAN 且不自动快速重试；RATE_LIMITED/
PLATFORM_TEMPORARY 由 Temporal Timer 有界重试；URL_INVALID、RIGHTS_REQUIRED、
SELECTOR_CHANGED 等永久失败直接终止。

## 决策 8：Task Lease 必须补齐的既有缺口

- Edge Agent 在每个任务执行期间以 `lease_ttl / 3` 周期续租；续租 409 后禁止迟到提交。
- WorkerTask 增加 CANCELLED，旧 lease 的 renew/complete/fail 均返回冲突。
- WorkerDispatch 持久化 execution policy、workflow id、artifact ids、resource limits、
  credential handles 和优先级；入库前先经 TaskEnvelope secret-key 校验。
- WAITING_FOR_HUMAN 属于 Workflow/ingest projection，不加入 WorkerTask 执行状态。

## 决策 9：测试与安全证据

所有自动化使用脱敏 JSON/HTML Fixture、注入 canary 和程序生成的合成媒体。验收扫描 API
响应、任务参数、业务表、事件和日志；媒体 golden 比较 SHA/size/MIME 以及容器/时长/尺寸
声明，不只比较文件 hash。真实平台 smoke test 不进入 CI，默认关闭。
