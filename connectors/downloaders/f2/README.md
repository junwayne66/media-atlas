# f2 下载连接器（download.f2）

实现 provider-sdk 的 `DownloadConnector` 端口（`docs/modules/41 §2/§3`）。抖音下载优先级 **#2**
（官方能力之上、yt-dlp 之上）；TikTok 优先级 **#3**（yt-dlp 之下）。优先级/回退由 provider-sdk
的 `DownloadRouter` 编排——本连接器只负责"用 f2 下一条"。

## 与 yt-dlp 共享（单实现单测试，安全逻辑不分叉）

- 凭据端口 `CookieResolver`（不透明 `credential_handle` → 短时 cookie 文件）
- 下载错误映射 `map_download_error`（§12 码，含中文/f2 签名，挑战优先）
- 下载辅助 `scrub_metadata` / `sha256_file` / `locate_downloaded_media`（dest_dir 约束）

均来自 `videoforge_provider_sdk`。连接器包只依赖 contracts + provider-sdk。

## 安全立场（README §4 / 53 §10 停止条件）

- **实时下载默认未启用**：默认 runner `UnconfiguredF2Runner` 返回 `UNCONFIGURED`；真实下载须
  显式构造 `SubprocessF2Runner(binary=...)`（需真实 f2 二进制 + 真实资源/账号）。
- **版本锁定** `f2==0.0.1.7`（`runner.PINNED_VERSION` ↔ descriptor，测试断言）。
- **Cookie 走不透明 `credential_handle`**：只有 cookie 文件**路径**进 argv，句柄/内容不入日志。
- **注入安全**：`build_argv` 可控值一律 `--opt=value` 单 token，无位置参数 URL，参数数组子进程执行。
- **验证码/风控 → `CHALLENGE`**：转人工，绝不绕过；`DownloadRouter` 也不会因 CHALLENGE 去换别的下载器。
- **平台限定**：仅抖音（`dy`）/TikTok（`tk`）子命令；其余平台 `SOURCE_UNAVAILABLE`。
- **元数据脱敏**：`raw_metadata` 递归剔除 cookie/authorization/token/http_headers 键。
- **手工导入始终可用**：`resolve_local_file(path)` → `platform="manual"`（f2 不下载 manual）。

## 结构

- `runner.py` — `F2Runner` 协议 + `Unconfigured`（默认）/`Subprocess`（真实，args-array）后端。
- `connector.py` — `F2DownloadConnector`（`build_argv`/`download`/`probe`/`health_check`）。
- `fixtures/info_dict.json` — 中性合成 f2 输出（含机密字段以测脱敏），非真实平台响应。
- `tests/` — 契约测试，全程 `FixtureF2Runner`，绝不跑真实二进制。

注：f2 自动选最佳清晰度，不吃 `format_selector`；manifest 仍如实记录请求的 format（作请求身份/Cache Key）。
真实 `SubprocessF2Runner` 的 f2 CLI 输出适配在启用实时下载时最终确定（停止条件前不接真实抓取）。
