# 热门开源项目调研与复用策略

> 星标是 2026-07-19 调研时的近似值，只用于判断社区热度，不作为技术选型的唯一依据。代码许可证与模型权重、字体、二进制依赖、素材服务条款必须分别核验。

## 1. 结论先行

- 不直接 fork 一个“大而全”项目作为平台。
- 以 `video-autopilot-kit` 的方法论、模板和 QA Gate 为参考；采用其 Programmatic 思路，CapCut 路线只做适配器。
- 以 `MoneyPrinterTurbo` 参考主题到成片和多 Provider 设计。
- 以 `VideoLingo` 参考字幕切分、翻译反思、配音工程；以 WhisperX 作为词级时间对齐能力。
- 以 `FunClip`、`ClipsAI`、`auto-editor` 参考热门片段、说话人重构图和静音/运动剪辑。
- `yt-dlp` + `f2` 作为首期获取层候选；所有非官方平台接口必须封装、监控、可熔断。
- OTIO 为时间线交换底座；FFmpeg 为确定性媒体处理；Remotion 负责动态模板/预览，但需先确认其特殊商业许可证是否适用。
- 官方发布 API 优先；Postiz/Mixpost 只参考调度、OAuth、日历和 Temporal 模式。
- GPL/AGPL 项目默认“概念参考或进程隔离”，不复制到宽松许可证核心。

## 2. 项目矩阵

| 项目 | 热度 | 许可证 | 可借鉴能力 | 建议 |
|---|---:|---|---|---|
| [video-autopilot-kit](https://github.com/Hao0321/video-autopilot-kit) | ~1.3k | MIT | FFmpeg 路线、模板/SOP、delivery QA、B-roll 审计、字幕素材匹配 | **概念+部分代码复用**；Programmatic 为主，CapCut 不进核心 |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | ~98.1k | MIT | 主题→脚本→素材→字幕/TTS→成片，Web/API/CLI，多 Provider | **参考 Provider 和生成流水线**；不要把其任务目录当领域模型 |
| [VideoLingo](https://github.com/Huanshere/VideoLingo) | ~17.8k | Apache-2.0 | WhisperX、字幕切分、术语、翻译反思、配音、暂停恢复 | **重点参考/可抽取模块**；重写为 Provider + 结构化合同 |
| [KrillinAI](https://github.com/krillinai/KrillinAI) | ~10.5k | GPL-3.0 | 下载、转录、翻译、配音、横竖屏、封面、阶段式 CLI | **概念参考或独立 Sidecar**；禁止复制 GPL 代码进核心 |
| [pyVideoTrans](https://github.com/jianchang512/pyvideotrans) | ~18.4k | GPL-3.0；项目声明需另核对 | 多角色配音、声音克隆、本地/云模型、交互式校订 | **概念参考/独立进程**；商业使用前单独评审 |
| [FunClip](https://github.com/modelscope/FunClip) | ~6k | MIT；模型权重另计 | 中文 ASR、热词、说话人、按文本/LLM 剪辑 | **可集成或重写 Activity**，适合中文热点片段 |
| [ClipsAI](https://github.com/ClipsAI/clipsai) | ~522 | MIT | 基于转录的片段提取、说话人中心 16:9→9:16 | **算法参考/可试接**；样本类型偏播客/访谈 |
| [auto-editor](https://github.com/WyattBlue/auto-editor) | ~4.6k | Unlicense（发布二进制另计） | 静音/运动剪辑、多 NLE 导出 | **CLI Adapter 或算法参考** |
| [WhisperX](https://github.com/m-bain/whisperX) | ~23.1k | BSD-2-Clause | 词级时间戳、强制对齐、说话人分离 | **ASR Provider 之一**；macOS 首期用云/CPU 降级 |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | ~179k | Unlicense；依赖另计 | 多站点下载、字幕、Cookies、插件、后处理 | **核心 Download Provider**，锁版本并做回归样例 |
| [f2](https://github.com/Johnserf-Seed/f2) | ~2.6k | Apache-2.0 | 抖音/TikTok 等平台下载和数据接口 | **抖音/TikTok Adapter 候选**，必须配健康探针 |
| [TikTokDownloader / DouK](https://github.com/JoeanAmier/TikTokDownloader) | 热门 | GPL-3.0 | 抖音/TikTok 榜单、搜索、评论、批量下载 | **仅研究**；README 已说明加密参数算法过期/不再维护 |
| [TikTok-Api](https://github.com/davidteather/TikTok-Api) | 热门 | MIT | TikTok 元数据/Trending 的非官方 Python 包装 | **备用采集 Adapter**；易受 Cookie/签名变化影响 |
| [Remotion](https://github.com/remotion-dev/remotion) | ~53.7k | 特殊许可证 | React 动态视频、Player、批渲染、模板系统 | **有条件采用**；在商业规模前确认公司许可证 |
| [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) | ~1.9k | Apache-2.0 | 稳定时间线模型、FCPXML/AAF/EDL 等适配器 | **核心时间线交换层** |
| [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) | ~4k | Apache-2.0 | 剪映草稿、SRT、特效/转场/模板 | **Best-effort 导出插件**；新版草稿加密、macOS 不支持自动导出 |
| [Postiz](https://github.com/gitroomhq/postiz-app) | ~33.5k | AGPL-3.0 | 自托管社媒日历、OAuth、分析、Temporal 工作流 | **架构参考或独立服务**；不复制 AGPL 代码 |
| [Mixpost](https://github.com/inovector/mixpost) | ~3.4k | MIT（Lite） | 账号、排期、媒体库、模板、分析 | **参考 UI/领域**；Lite/Pro 功能边界需确认 |
| [Tauri](https://github.com/tauri-apps/tauri) | 热门 | Apache-2.0/MIT | 跨平台桌面壳、Rust 后端、系统 WebView | **桌面端核心** |
| [Playwright](https://github.com/microsoft/playwright) | 热门 | Apache-2.0 | Chromium/Firefox/WebKit 自动化、持久会话 | **浏览器发布 Adapter**；挑战时停给人工 |
| [Appium](https://github.com/appium/appium) | 热门 | Apache-2.0 | WebDriver 真机自动化、可扩展驱动 | **Android 发布主框架** |
| [uiautomator2](https://github.com/openatx/uiautomator2) | 热门 | MIT | Android UIAutomator 的 Python/HTTP 封装 | **Android 轻量后备/定位器工具** |
| [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) | ~22.3k | 代码/权重分别核验 | 中英多语 TTS、零样本声音复刻、部署 | **TTS Provider 候选**；首期云 GPU |
| [MuseTalk](https://github.com/TMElyralab/MuseTalk) | 热门 | 代码/权重分别核验 | 多语言音频驱动口型 | **可选 LipSync Provider**；只对高置信人脸段运行 |

## 3. 许可证隔离等级

| 等级 | 含义 | 处理方式 |
|---|---|---|
| L0 | MIT/Apache/BSD/Unlicense，依赖也已核验 | 可作为库或纳入代码，但保留 NOTICE/SBOM |
| L1 | 代码宽松，模型/二进制/素材条款不同 | Provider 插件；运行前显示模型/资源许可证 |
| L2 | 特殊商业许可证 | 只通过稳定公开 API 使用；部署规模变化触发评审 |
| L3 | GPL/AGPL 或额外用途声明 | 独立进程/容器或只参考思想；默认不分发其代码 |
| L4 | 非官方接口、签名/页面高度易变 | 独立 Connector；版本锁定、健康检查、熔断和人工回退 |

CI 必须生成 SBOM，并维护 `third_party_manifest.yaml`：仓库、版本/提交、许可证、模型卡、用途、隔离等级、归属模块。

## 4. 对参考项目的具体吸收方式

### 4.1 video-autopilot-kit

吸收：

- Programmatic FFmpeg 流水线。
- `SETUP` 问卷→频道画像/模板配置的思想。
- B-roll 与字幕语义匹配。
- 黑帧、频闪、死空档、字幕同步、B-roll 占比等 QA Gate。
- 可重放演示和交付清单。

不吸收为核心：

- CapCut Computer Use。
- 版本敏感的草稿 JSON 直改。
- 以本地目录和个人配置为中心的运行模型。

### 4.2 MoneyPrinterTurbo

吸收“主题→脚本→检索词→素材→字幕/TTS→渲染”的阶段划分和 Provider 多样性；用本系统的 `CreativeBrief`、`AssetPlan`、`TimelineVersion` 重写阶段接口。

### 4.3 VideoLingo

吸收字幕切分、术语表、Translate→Reflect→Adapt、时长约束和配音后处理；避免直接延续单工作目录和强耦合 UI。

### 4.4 Postiz

吸收 Temporal 处理发布长任务、连接器隔离、OAuth、内容日历和分析的结构。因为 AGPL，不把其实现代码复制进本项目。

## 5. 明确不做的复用

- 不将某个下载器暴露的响应 JSON 直接作为数据库表结构。
- 不将 WhisperX、FunClip 或 VideoLingo 的目录当作项目状态。
- 不把剪映/CapCut 草稿当作唯一可编辑成果。
- 不依赖单个非官方签名算法完成热点、下载或发布。
- 不把平台自动化写成跨模块共享的 UI 坐标脚本。

