# 技术栈与 ADR

## 1. 推荐栈

| 层 | 技术 | 选择理由 |
|---|---|---|
| Desktop | Tauri 2 + Rust | 跨平台、小体积、可管理 Sidecar/Keychain/本地文件 |
| Web/Desktop UI | Vue 3 + TypeScript + Vite | 两个端共用组件和领域 SDK，适合管理/审核界面 |
| API | Python 3.11 + FastAPI + Pydantic | AI/媒体生态强、OpenAPI/结构化合同成熟 |
| Workflow | Temporal Python SDK | 长任务、Timer、人审等待、重试、补偿和可视化 |
| DB | PostgreSQL + pgvector | 事务领域数据 + 多语语义检索 |
| Cache/Limit | Redis | 缓存、限流、短期锁；不承载唯一任务状态 |
| Object Store | S3 API / MinIO | 大文件、分片、预签名 URL、部署可替换 |
| Media | FFmpeg/ffprobe | 确定性编解码、滤镜、音频和 QC 基础 |
| Timeline | CreativeTimeline + OpenTimelineIO | 领域扩展 + NLE 交换，避免编辑器私有格式锁定 |
| Motion/Preview | Remotion + React 子包 | 动态字幕、信息卡、模板和 Player；商业许可证需评审 |
| ASR | whisper.cpp/faster-whisper + WhisperX/FunASR Provider | macOS 轻量本地 + 云端精对齐/中文热词 |
| OCR | PaddleOCR Provider + 跟踪 | 中英覆盖、可本地运行；保留云 OCR/VLM fallback |
| Scene | PySceneDetect + FFmpeg | 成熟、可重放、本地低成本 |
| Automation | Playwright + Appium/UiAutomator2 | Web 与 Android 真机发布适配 |
| Observability | OpenTelemetry + Prometheus/Grafana/Loki | 跨 API/Workflow/Worker 链路 |
| Packaging | Docker Compose + Tauri Bundler | 单机自托管和跨平台桌面发布 |

## 2. ADR-001：模块化单体，不从微服务起步

**决定**：API/领域/连接器注册在同一 FastAPI 部署中，媒体和 GPU Worker 独立。  
**原因**：当前吞吐小，事务一致性和迭代速度更重要。  
**约束**：各模块有独立 package、service、repository 和 migration 命名空间；跨域通过 service/event，不直接 import repository。

## 3. ADR-002：Temporal 为任务真值

**决定**：长任务的状态、Timer、重试、人审等待由 Temporal 管理。  
**不采用**：仅 Celery/RQ + 状态表。媒体流程可能运行数小时并跨桌面离线、人审和平台回调，补齐这些能力会重复造编排器。  
**边界**：高频细粒度帧任务不逐帧建 Activity；一个 Activity 处理一个可重试的媒体阶段。

## 4. ADR-003：CreativeTimeline 为领域真值

**决定**：业务扩展字段存在 `CreativeTimeline`，OTIO 用于交换，Render Graph 用于执行。  
**不采用**：CapCut/剪映 JSON、Remotion React 树或 FFmpeg 命令作为项目真值。  
**原因**：它们分别版本敏感、渲染器相关、不可审阅。

## 5. ADR-004：Hybrid Worker

**决定**：Desktop Edge Agent 与 Cloud Worker 实现相同 Task Protocol。  
**本地默认**：媒体探测、下载、代理、FFmpeg、OCR、快速 ASR、渲染。  
**云默认**：大 LLM/VLM、高质量 TTS、GPU 口型、生成式视频、词级精对齐。  
**覆盖**：项目/任务可选择 local-only/cloud-only。

## 6. ADR-005：官方发布优先，多层降级

**决定**：同平台发布实现多个 Connector，由 Capability Registry 动态选择。  
**原因**：平台 API 审核/能力不同，网页/App 也会变化。  
**安全边界**：所有非官方 UI 自动化均可停给人工，不处理验证码绕过。

## 7. ADR-006：Remotion 有条件采用

Remotion 适合模板、字幕、图卡和预览，但使用特殊许可证。实现时：

- 封装为 `RenderProvider`，核心时间线不依赖其组件类型。
- 在 `third_party_manifest.yaml` 记录版本和许可判断。
- 若商业规模/公司条件不满足，替换为 Web Canvas/FFmpeg overlay 或购买许可。
- FFmpeg 最终合成链始终可用。

## 8. Python 环境

建议使用 `uv` 管理：

```text
pyproject.toml
uv.lock
dependency-groups:
  api
  workflow
  media-base
  asr-local
  ocr-local
  gpu-optional
```

重依赖 Provider 分独立进程/镜像，避免 WhisperX、Paddle、Torch、FunASR 相互锁死版本。首期 macOS 不安装 CUDA 依赖组。

## 9. Node/Rust 环境

- PNPM workspace + 锁文件。
- UI 使用 TypeScript strict。
- Remotion 在独立 package，避免 Web 管理台被 React 依赖污染；可通过 JSON Props/Player iframe 集成。
- Rust stable 固定 `rust-toolchain.toml`。
- Tauri 命令只暴露白名单操作；媒体任务由 Sidecar Task Protocol 执行。

## 10. FFmpeg 分发

可选两种策略：

1. Pilot：安装向导检测 Homebrew FFmpeg 并记录版本。
2. 发布：提供受校验和保护的每平台构建下载器，展示其许可证/构建选项。

不得假定用户 PATH；`ToolchainRegistry` 保存实际二进制路径、版本、buildconf 和 hash。

## 11. 数据与 Migration

- SQLAlchemy 2 + Alembic。
- 主键使用 UUIDv7/ULID，外部不可枚举。
- 时间全部 UTC，展示层转换。
- JSONB 只保存版本化灵活结构，核心过滤/唯一性字段使用列。
- pgvector 用于热点、脚本、素材近邻，不存原二进制媒体。
- Outbox 表与领域写事务一致提交。

## 12. 测试栈

- Python：pytest、Hypothesis、testcontainers。
- TS：Vitest、Testing Library、Playwright（产品 UI E2E 与发布 Adapter 测试隔离）。
- Rust：cargo test。
- Workflow：Temporal time-skipping tests。
- Media：golden manifests + 小型合成媒体；比较帧/音频/时长而非只比较文件 hash。
- Connector：录制/脱敏 Fixture + 每日 Canary；禁止单元测试实时打平台。

## 13. 供应链

- 锁定依赖、容器 digest 和 Provider 版本。
- CI 生成 SBOM、许可证清单和漏洞扫描。
- 模型记录 model card、权重 hash、许可证和下载来源。
- Sidecar 和桌面更新包签名；macOS notarization。

