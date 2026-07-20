# Coder Agent 实施路线与任务清单

## 1. 执行方法

每个 Task 形成一个小 PR/提交，内容包括：实现、测试、Migration/Schema、文档和验收证据。任务只能在依赖完成后进入 `in_progress`。平台实时接口或真实模型先用 Fake Provider 打通端到端，再替换实现。

## 2. P0：工程与领域地基

### VF-001 Bootstrap Monorepo

依赖：无。  
产物：Python/PNPM/Rust workspace、lint/test/CI、Compose、基础 README/AGENTS。  
DoD：`make/just dev`（或等价跨平台命令）启动 API、Web、Postgres、MinIO、Temporal；CI 在 macOS/Linux 通过。

### VF-002 Contracts First

依赖：VF-001。  
产物：Project、Artifact、TaskEnvelope、ProviderDescriptor、ProblemDetail JSON Schema；Python/TS 生成类型。  
DoD：Schema round-trip、向后兼容和无效样例测试。

### VF-003 Persistence + Outbox

依赖：VF-002。  
产物：Postgres schema、Alembic、repositories、transactional outbox。  
DoD：并发版本冲突、事件去重和 rollback 测试。

### VF-004 Artifact Store

依赖：VF-002/003。  
产物：S3/MinIO、本地 Cache、hash/probe、预签名 URL、临时上传提交。  
DoD：中断上传、重复 Artifact、不同来源同哈希测试。

### VF-005 Temporal Skeleton

依赖：VF-003/004。  
产物：基础 Workflow、Operation API、retry policy、Signal/Query、time-skipping tests。  
DoD：进程重启后 Workflow 继续；人工等待可 signal 恢复。

### VF-006 Provider Registry

依赖：VF-002。  
产物：Provider SDK、descriptor loader、health/circuit breaker、Fake Providers。  
DoD：能力/语言/位置/成本路由和健康降级测试。

### VF-007 Desktop + Edge Agent

依赖：VF-002/004/006。  
产物：Tauri 壳、Worker 注册/心跳/Lease、Keychain Broker、工具链探测。  
DoD：关闭 UI 后 Sidecar 继续；Lease 过期可重分配；Secret 不出现在日志。

**P0 Exit**：Fake Source→Fake Render 的长 Workflow 可由 macOS Desktop Worker 完成，全部 Artifact 和状态可查看。

## 3. P1：热点与获取

### VF-101 Trend Domain + Snapshots

依赖：P0。  
实现 Snapshot、Cluster、Score、阶段状态机和 reason codes。使用合成时间序列验证速度/加速度/衰减。

### VF-102 Douyin Discovery Connector

依赖：VF-101/006。  
优先官方可用能力；再接隔离公开信号 Adapter；提供手工导入。含 descriptor、Fixture、Canary、熔断。

### VF-103 TikTok Discovery Connector

同 VF-102；非官方接口作为 L4 Provider，空结果必须可诊断。

### VF-104 Trend UI

热度、阶段、证据、跨平台成员、人工拆分/合并和一键创建 Project。

### VF-105 URL Resolver + yt-dlp Adapter

短链、平台 ID、Cookie Handle、断点下载、错误映射和版本锁定。

### VF-106 f2 Adapter

抖音/TikTok 能力；与 yt-dlp 有清晰优先级和回退。

### VF-107 Fingerprint + Dedup

SHA、视频 pHash、音频/文本指纹和 duplicate group。

**P1 Exit**：50 个试点链接可导入或明确提示人工回退；热点 Top-20 有证据和可重放得分。

## 4. P2：理解与 Blueprint

### VF-201 Media Runtime

ffprobe、代理、音频提取、Scene、Face/运动基础特征；工具版本进入 Manifest。

### VF-202 ASR Providers

macOS 轻量本地 + WhisperX 云 Worker + 中文热词 Provider。输出统一词级合同。

### VF-203 OCR + TextTrack

中英 OCR、多帧投票、跟踪、类型分类和审核可视化。

### VF-204 VLM Sampling

代表帧选择、批量/缓存、低置信触发；禁止逐帧云调用。

### VF-205 Blueprint Fusion

Claim evidence、Beat、Shot、Audio/Caption/Pacing；Schema/时间校验。

### VF-206 Analysis Review UI

视频跳转、转录修订、OCR Track、Beat/Claim 可视化。

**P2 Exit**：20 条中英样本 Blueprint 可追溯到证据；局部 Provider 重跑不重复下载。

## 5. P3：二创与剪辑

### VF-301 Creative Brief + Claim Table

Opportunity→Brief；新增事实状态、角度、受众、平台和时长预算。

### VF-302 Structure Rewrite Engine

Beat Template、Canonical Script、重复度/事实/时长规则和版本 UI。

### VF-303 Highlight Ranker

窗口生成、特征、MMR、理由；人工标签记录。

### VF-304 Source Re-edit Planner

保留/删除/重排、静音、连续性、重构图建议。

### VF-305 Asset Resolver

本地库优先；Stock/Generated 为 Fake→真实 Provider；来源/许可记录。

### VF-306 CreativeTimeline + OTIO

RationalTime、轨道、Segment、Validator、OTIO 映射和版本。

### VF-307 FFmpeg Compiler

参数数组、Filter Graph、音频/字幕/构图、Manifest、Golden Media Tests。

### VF-308 Remotion Template + Player

信息卡、动态字幕、品牌 tokens、代理预览；许可证记录。

### VF-309 QA Gates

实现黑帧、冻帧、频闪、死空档、字幕同步、B-roll 审计、响度和时长。

### VF-310 Exporters

OTIO/FCPXML/DaVinci；剪映/CapCut 插件只标 experimental。

**P3 Exit**：两种模式各生成 10 条可审样本；代理与最终切点差 <1 帧；修改一句可局部重跑。

## 6. P4：中英本地化

### VF-401 Terminology + Canonical Localization

术语、Translate/Reflect/Adapt、Claim diff、时长预算。

### VF-402 Subtitle Engine

语义分段、阅读速度、安全区、ASS/SRT/Timeline Overlay。

### VF-403 On-screen Text Localization

TextTrack 策略、Clean Plate/覆盖、布局和跟踪；低质量回退信息卡。

### VF-404 TTS Providers

统一接口、Voice Profile、WordTimings、预览/高质量 Provider。

### VF-405 Duration Fit + Audio Mix

改写、语速、镜头 Hold、Ducking、响度、Room Tone。

### VF-406 LipSync Provider

资格判断、云 GPU Adapter、局部合成、QA 和 B-roll 回退。

### VF-407 Localization Review

原文/译文/Adapt/波形/视频并排，句级批准和局部重跑。

**P4 Exit**：20 条中英样本通过数字/术语/事实、字幕和音画验收；口型故障不阻塞。

## 7. P5：审核与发布

### VF-501 Review Policy + Queue

ALWAYS/NEW_TEMPLATE_ONLY/AUTO、版本签名、修改失效、Trusted Template 状态机。

### VF-502 Platform Preflight

分辨率、编码、文件、时长、标题/标签、账号/授权能力。

### VF-503 TikTok Official Publish

Creator Info、Direct Post/Upload、状态/Webhook、应用审核状态提示、幂等。

### VF-504 Douyin Official Publish

OpenAPI/分享能力、状态、错误映射、授权数据。

### VF-505 Browser Publish Adapter

持久 Profile、选择器、截图、挑战暂停、Canary。

### VF-506 Android Device Adapter

Appium/UiAutomator2、ADB、账号/设备确认、Share Intent、发布证据。

### VF-507 Calendar + Reconciliation

Temporal Timer、未知结果查询、重复帖子防护、手工完成。

**P5 Exit**：测试账号端到端发布；网络超时重试不重复发；挑战必停给人工。

## 8. P6：效果反馈

### VF-601 Metrics Connectors

平台指标快照、限流和 null 语义。

### VF-602 Performance Dashboard

账号基线、模板/Hook/时长/语言/发布时间分组。

### VF-603 Learning Signals

人工选择/驳回、QA、修改、热点和表现的可解释关联。

### VF-604 Ranker Calibration

在样本足够后校准热点/Highlight；先离线评估再少量探索。

## 9. Task PR 模板

```markdown
Task: VF-xxx
Goal:
Non-goals:
Contracts changed:
Migrations:
Provider/license changes:
Implementation:
Tests:
Manual verification:
Rollback/feature flag:
Known limitations:
```

## 10. Coder Agent 停止条件

遇到以下情况不得自行扩大范围：

- 需要真实平台账号、App Review 或付费 Provider 凭据。
- 许可证/模型条款不明。
- 平台出现验证码/风控挑战。
- 需要改变核心 ADR、时间线真值或二创模式定义。
- Golden 样本出现质量回退而无法解释。

此时应保留可运行 Fake/Manual Adapter，输出阻塞证据和最小决策问题。

