# 模块总纲

## 1. 模块地图

| ID | 模块 | 核心职责 | 主要输入 | 主要输出 | 优先级 |
|---|---|---|---|---|---|
| M01 | Trend Intelligence | 采集、聚类、热度/相关性/饱和度评分 | 平台快照、关键词、频道画像 | TrendCluster、CreativeOpportunity | P1 |
| M02 | Acquisition | URL 解析、下载、去重、代理文件、来源记录 | URL、账号/榜单条目 | SourceAsset、MediaArtifact | P1 |
| M03 | Understanding | ASR/OCR/镜头/人物/音频/VLM 分析 | SourceAsset | VideoAnalysis、VideoBlueprint | P1 |
| M04 | Creative Planning | 结构重写、重剪策略、脚本与素材规划 | Opportunity、Blueprint、模板 | CreativeBrief、ScriptVersion、AssetPlan | P1 |
| M05 | Highlight Ranking | 热门片段窗口生成、排序和去重 | Transcript、Scenes、Topic | HighlightCandidate[] | P1 |
| M06 | Asset Resolver | 本地/商业/AI/数字人素材检索与生成 | AssetPlan | ResolvedAsset[] | P1/P2 |
| M07 | Timeline & Render | 统一时间线、预览、渲染、NLE 导出 | Script、Assets、模板 | TimelineVersion、RenderArtifact | P1 |
| M08 | Localization | 字幕、画面文字、翻译、TTS、同步、口型 | Timeline、Analysis | LocalizationVariant | P1 |
| M09 | Quality Control | 技术、语义、音画、字幕、平台预检 | Variant、Render | QCReport | P1 |
| M10 | Review | 人审、版本、批注、局部重跑、批准 | Variant、QCReport | ReviewDecision | P1 |
| M11 | Publishing | OAuth/API、浏览器、真机、排期、幂等 | ApprovedVariant、Account | PublishJob、PlatformPost | P1 |
| M12 | Analytics | 指标快照、归因、模板/选题反馈 | PlatformPost、指标 | PerformanceSnapshot、LearningSignal | P2 |
| M13 | Provider Registry | 模型、素材、平台能力注册与路由 | Provider 配置、Worker 能力 | CapabilityRoute | P0 |
| M14 | Orchestration | 长工作流、重试、人审等待、补偿 | Command/Event | WorkflowRun、TaskLease | P0 |
| M15 | Identity & Secrets | 用户、账号、密钥、审计 | OAuth/本地 Secret | CredentialRef、AuditEvent | P0 |

## 2. 强制数据边界

### 2.1 不可变对象

- `SourceSnapshot`：采集时的原始平台响应/页面证据。
- `SourceAsset`：输入媒体及其哈希、来源、获取方式。
- `AnalysisRun`：工具和模型版本固定的一次分析。
- `RenderArtifact`：每次渲染的输入 Manifest 和输出哈希。
- `PublishAttempt`：一次具体外部发布请求和响应。

### 2.2 可版本化对象

- `CreativeBrief`
- `ScriptVersion`
- `VideoBlueprint`
- `AssetPlan`
- `TimelineVersion`
- `LocalizationVariant`
- `ReviewDecision`
- `TemplateVersion`

可版本化对象只新增版本，不在原记录上覆盖历史。

## 3. 模块通信规则

- 同一控制中心内：通过领域服务方法和事务 Outbox 事件通信。
- 长任务：Temporal Workflow 调用 Activity。
- 桌面 Worker：通过 Task Lease API 长轮询/WS 通知领取任务，通过预签名 URL 读写 Artifact。
- 跨模块传递：只传 ID 和结构化合同，不传某个开源项目的临时目录。
- 二进制媒体：只进入对象存储或本地 Artifact Cache，不进入 PostgreSQL。
- AI 结果：保存原响应、解析后 JSON、Schema 版本、Prompt 版本、模型和成本。

## 4. Provider 类型

```text
SourceConnector       平台发现/元数据
DownloadProvider      媒体获取
ASRProvider           语音识别与时间对齐
OCRProvider           画面文字检测/识别/跟踪
LLMProvider           脚本、翻译、分类、评分
VLMProvider           场景理解、质量和素材匹配
TTSProvider           合成语音/声音克隆
LipSyncProvider       口型生成
StockMediaProvider    商业/公共素材搜索
GenerativeMediaProvider AI 图片/视频生成
RenderProvider        FFmpeg/Remotion/云渲染
TimelineExporter      OTIO/FCPXML/DaVinci/CapCut
PublishConnector      官方 API/浏览器/真机发布
MetricsConnector      平台数据回收
```

每个 Provider 都必须声明：`capabilities`、`languages`、`platforms`、`cost_model`、`execution_location`、`license_notes`、`health`、`version`。

## 5. 首期能力路由

| 任务 | 默认位置 | 默认实现 | 降级 |
|---|---|---|---|
| FFmpeg/ffprobe | macOS 本地 | Sidecar CLI | 服务端 CPU Worker |
| ASR | 本地优先 | whisper.cpp/轻量 faster-whisper；需要词级对齐时 WhisperX 云 Worker | 云 ASR API |
| OCR | 本地 | PaddleOCR/系统可用 OCR + 跟踪 | 云 OCR/VLM |
| 镜头检测 | 本地 | PySceneDetect/FFmpeg | VLM 粗分段 |
| LLM/VLM | 云端 | 可配置 OpenAI-like Provider | 本地小模型 |
| TTS | 云端优先 | Provider Registry | 系统/本地 TTS |
| 口型 | 云端 GPU | MuseTalk 类 Provider | 不改口型，改用 B-roll/切镜 |
| 渲染 | 本地 | FFmpeg + Remotion | 服务端 Worker |
| 发布 | 服务端编排 | 官方 API | 桌面浏览器/Android 真机 |

## 6. QA Gate 顺序

1. `INPUT_QA`：媒体可解码、音轨/时基有效、输入哈希完整。
2. `ANALYSIS_QA`：ASR/OCR 覆盖、镜头边界、语言/人物置信度。
3. `CREATIVE_QA`：事实、脚本结构、重复度、素材缺口。
4. `TIMELINE_QA`：空洞、重叠、越界、字幕/语音时长。
5. `RENDER_QA`：黑帧、冻帧、闪烁、响度、峰值、音画漂移。
6. `LOCALIZATION_QA`：未翻译文字、CPS、语义一致性、配音自然度。
7. `PLATFORM_QA`：分辨率、编码、时长、文件大小、标题/标签规则。
8. `DELIVERY_QA`：成片哈希、缩略图、发布元数据、审批签名。

`video-autopilot-kit` 的 delivery QA、B-roll audit、caption/B-roll matching 思路应在 M09 中重新实现为通用 Gate，而不是直接耦合其目录结构。

