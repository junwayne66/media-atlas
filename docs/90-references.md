# 参考资料

调研基线：2026-07-19。平台规则、API 能力、项目版本和许可证会变化，实施前应再次核对官方来源并锁定版本。

## 1. 参考系统与视频创作

- [Hao0321/video-autopilot-kit](https://github.com/Hao0321/video-autopilot-kit)：Programmatic FFmpeg、CapCut-assisted、模板/SOP 和 QA Gate。
- [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)：主题到短视频、多 Provider、Web/API/CLI、Docker。
- [RayVentura/ShortGPT](https://github.com/RayVentura/ShortGPT)：短视频生成流程参考。
- [Huanshere/VideoLingo](https://github.com/Huanshere/VideoLingo)：字幕切分、翻译、对齐和配音。
- [krillinai/KrillinAI](https://github.com/krillinai/KrillinAI)：多阶段视频翻译/配音/横竖屏流程；GPL-3.0。
- [jianchang512/pyvideotrans](https://github.com/jianchang512/pyvideotrans)：多模型转录、翻译、配音；GPL-3.0/项目声明需单独复核。

## 2. 下载、平台数据与热点

- [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp)：多站点下载、字幕、Cookie 和插件。
- [Johnserf-Seed/f2](https://github.com/Johnserf-Seed/f2)：抖音/TikTok 等平台数据与下载 Adapter 候选。
- [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader)：抖音/TikTok 数据/下载研究；其 README 已提示部分加密参数能力失效。
- [davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api)：非官方 TikTok Python API；需隔离和健康检查。
- [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader)：抖音下载、重试、SQLite 去重和浏览器回退参考。

## 3. 剪辑、时间线与渲染

- [modelscope/FunClip](https://github.com/modelscope/FunClip)：FunASR、热词、说话人和 LLM 剪辑。
- [ClipsAI/clipsai](https://github.com/ClipsAI/clipsai)：转录驱动片段和说话人重构图。
- [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor)：静音/运动剪辑和 NLE 导出。
- [AcademySoftwareFoundation/OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO)：稳定时间线 API/交换格式和适配器。
- [remotion-dev/remotion](https://github.com/remotion-dev/remotion)：React 动态视频、Player 和批渲染；特殊许可证。
- [GuanYixuan/pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)：剪映草稿生成、字幕/模板；新版和 macOS 自动导出有限制。

## 4. ASR、TTS 与口型

- [m-bain/whisperX](https://github.com/m-bain/whisperX)：词级时间戳、强制对齐和说话人。
- [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)：CTranslate2 Whisper 推理。
- [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp)：CPU/Metal 友好的本地 Whisper。
- [modelscope/FunASR](https://github.com/modelscope/FunASR)：中文/多语 ASR、VAD、标点和热词。
- [FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice)：多语言零样本 TTS。
- [RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)：少样本/跨语种 TTS。
- [TMElyralab/MuseTalk](https://github.com/TMElyralab/MuseTalk)：多语言音频驱动口型。
- [KwaiVGI/LivePortrait](https://github.com/KwaiVGI/LivePortrait)：肖像动画参考。

## 5. 桌面、发布与调度

- [tauri-apps/tauri](https://github.com/tauri-apps/tauri)：跨平台桌面框架。
- [microsoft/playwright](https://github.com/microsoft/playwright)：浏览器自动化。
- [appium/appium](https://github.com/appium/appium)：跨平台移动自动化。
- [appium/appium-uiautomator2-driver](https://github.com/appium/appium-uiautomator2-driver)：Android 真机驱动。
- [openatx/uiautomator2](https://github.com/openatx/uiautomator2)：Python/HTTP Android UIAutomator 封装。
- [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app)：自托管社媒调度、Temporal、OAuth 和分析；AGPL-3.0。
- [inovector/mixpost](https://github.com/inovector/mixpost)：自托管社媒管理 Lite；MIT，需区分 Pro 功能。
- [Temporal Documentation](https://docs.temporal.io/)：持久工作流。

## 6. 官方发布文档

- [TikTok Content Posting API — Direct Post](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)：Creator Info、初始化、上传与直接发布。
- [TikTok Content Posting API — Get Started](https://developers.tiktok.com/doc/content-posting-api-get-started)：Direct Post 配置与授权。
- [TikTok Content Posting Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines)：未审核客户端可见性限制和审核要求。
- [抖音内容发布接入方案](https://open.douyin.com/platform/resource/docs/ability/content-management/douyin-publish-solution)：OpenAPI 发布视频/图片、格式和限制。
- [抖音视频分享接入方案](https://open.douyin.com/platform/resource/docs/ability/content-management/douyin-share-solution)：分享 SDK 和话题等能力。
- [抖音 Android 分享](https://open.douyin.com/platform/resource/docs/develop/share/android)：分享到编辑/发布页的 SDK 流程。
- [抖音视频数据接入方案](https://open.douyin.com/platform/resource/docs/ability/open-data/video-data-solution)：授权账号视频数据。
- [YouTube Data API — Upload a Video](https://developers.google.com/youtube/v3/guides/uploading_a_video)：后续平台上传参考。
- [Instagram Content Publishing](https://developers.facebook.com/documentation/instagram-platform/content-publishing)：后续 Reels/内容发布参考。

## 7. 许可证注意

仓库许可证不自动覆盖模型权重、预编译二进制、字体、音乐、商业素材或平台 API 条款。真正接入前必须把具体版本/commit、许可证文本、模型卡和用途写入 `third_party_manifest.yaml`，并为 GPL/AGPL、特殊商业许可证和非官方接口设置相应隔离等级。

