# 首期 macOS 验证方案

## 1. 验证目标

首期只证明完整链路和架构边界，不要求 macOS 本地承担所有 AI 重计算。目标是：同一 Control Plane 下，Mac Desktop 能稳定处理本地媒体/审核/渲染，并把重型任务路由到云 Worker。

## 2. 建议基线

- 主验证：Apple Silicon M1 或更新，16GB RAM 起，预留 100GB 媒体缓存。
- macOS 14 或更新版本作为首期测试矩阵起点。
- Intel Mac 只保证架构可编译，首期不作为性能基线。
- Android 发布验证：一台专用 Android 真机 + 数据线，启用受控的 USB 调试。

具体最低版本在首次 Spike 后写入 Toolchain Matrix，不在业务代码硬编码。

## 3. 本地组件

```text
Tauri Desktop
Edge Agent Sidecar
FFmpeg/ffprobe
Python Media Runtime（无 CUDA）
Node/Remotion Renderer
Local Artifact Cache
macOS Keychain Broker
Docker Desktop: API/Web/Temporal/Postgres/Redis/MinIO
ADB/Appium（可选发布设备）
```

## 4. 计算分工

| 任务 | Mac 默认 | 原因 |
|---|---|---|
| 下载、Probe、代理 | 本地 | 数据就近、成本低 |
| Scene/音频/指纹 | 本地 | CPU 足够、确定性 |
| OCR | 本地 | 中英短视频可满足 |
| 快速 ASR | 本地 | 预览和隐私 |
| 词级精对齐/说话人 | 云优先 | WhisperX/CUDA 生态更稳定 |
| LLM/VLM | 云 | 质量与维护 |
| TTS | 云优先 | 高质量与多音色 |
| LipSync/生成式视频 | 云 GPU | Mac 首期不承担 |
| FFmpeg/Remotion 渲染 | 本地 | 交互和素材就近 |
| 浏览器发布 | Mac Desktop | 使用本地登录会话 |
| Android 发布 | Mac + 真机 | ADB/Appium 控制 |

## 5. 安装与自检

安装向导应自动检查：

- CPU 架构、macOS 版本、磁盘和 RAM。
- Docker/服务健康。
- FFmpeg/ffprobe 路径、版本、编码器和字体。
- Python Media Sidecar、Node Renderer、Chromium。
- Keychain 读写权限。
- 屏幕录制/辅助功能权限（仅在确有发布/预览需要时申请）。
- ADB 设备、授权指纹、Appium Driver（可选）。
- 云 Provider 连通性和预算。

自检结果以 Capability 上报，不用“安装成功”一个布尔值。

## 6. macOS 权限

- 文件选择使用用户明确选择的目录/Bookmark，不默认扫描整个磁盘。
- Keychain 用于 Cookie/本地 Provider Key 句柄。
- 浏览器自动化使用独立 Profile，不复用用户日常浏览器默认 Profile。
- 若使用系统辅助功能/屏幕录制，UI 解释用途并允许不授权；不授权时隐藏对应 Capability。
- Tauri Sidecar、应用包和更新必须签名/notarize。

## 7. FFmpeg 与硬件编码

- 首期同时支持软件编码和 VideoToolbox，默认先以质量/兼容性 Golden Test 决定。
- H.264 + AAC MP4 为抖音/TikTok 基础交付格式。
- 硬件编码的颜色、关键帧、码率和 B-frame 行为与软件编码分别建测试基线。
- 字体必须显式打包/登记，不能假定每台 Mac 有同名 CJK 字体。

## 8. Remotion 注意事项

- Renderer 使用固定 Chromium/依赖版本。
- 限制并发，防止 16GB 机器内存峰值过高。
- 预览只加载 Proxy，最终渲染读取 Mezzanine。
- 动态模板输出与 FFmpeg 合成使用同一帧率/色彩配置。
- 记录 Remotion 特殊许可证评审结果。

## 9. Android 真机

- 每台设备建立 `DeviceBinding`，记录 ADB 指纹、设备型号、系统/App 版本和绑定账号。
- 媒体推送到专用目录，发布完成后清理。
- 发布前后截图和账号验证。
- USB 断开、锁屏或 App 更新时进入待人工，不自动换设备/账号。
- 首期只串行一台设备，避免设备农场复杂度。

## 10. Pilot 场景

1. 抖音中文热点 → 结构重写 → 中/英两个版本 → 本地渲染 → 人审 → 测试账号发布。
2. TikTok 英文链接 → 原片重剪 → 英/中两个版本 → 画面文字重绘 → 发布。
3. Desktop 在 ASR/渲染中退出，Sidecar/Workflow 恢复。
4. 云 TTS 或口型失败，自动换 Provider/回退 B-roll。
5. 浏览器登录失效或真机弹挑战，进入人工等待。
6. 发布请求未知结果，自动 Reconcile 且不重复发布。
7. 24/72 小时指标回收并展示模板/版本归因。

## 11. Pilot 通过标准

- 每个场景至少连续成功 3 次。
- 20 条视频/日的模拟队列不丢任务、不重复 Artifact/帖子。
- Desktop UI 崩溃不影响 Control Plane 状态。
- 本地磁盘水位可告警和安全清理，原始输入不被误删。
- 所有重型任务都能在无本地 CUDA 的情况下路由/降级。
- macOS 专属实现仅存在 Platform Adapter，不渗入领域/Workflow。

