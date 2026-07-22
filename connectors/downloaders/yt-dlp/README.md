# yt-dlp 下载连接器（download.yt_dlp）

实现 provider-sdk 的 `DownloadConnector` 端口（`docs/modules/41 §3` ResolveSource→AcquireMedia，
`50-tech-stack.md` ADR「yt-dlp Adapter」）。TikTok 优先级 #2（官方授权导出优先），
抖音优先级低于 f2（VF-106）。

## 安全立场（README §4 / 53 §10 停止条件）

- **实时下载默认未启用**：`YtDlpDownloadConnector()` 默认 runner 是 `UnconfiguredYtDlpRunner`，
  返回 `UNCONFIGURED`，不触网、不静默假装成功。真实下载须显式构造
  `SubprocessYtDlpRunner(binary=...)`（需真实 yt-dlp 二进制 + 真实资源/账号）。
- **版本锁定** `yt-dlp==2025.01.15`（`runner.PINNED_VERSION` 与 `descriptor.yaml` 同步）；
  真实 runner 探测 `--version` 并写入 `AcquisitionManifest.tool_version`，升级须重跑契约测试。
- **Cookie 走不透明 `credential_handle`**：请求绝不带明文 Cookie；`CookieResolver` 把句柄
  换成短时 cookie 文件，只有文件**路径**进 argv（内容才是机密，绝不入日志）。默认
  `UnconfiguredCookieResolver`：给了句柄却解析不了 → `AUTH_REQUIRED`（转人工），不静默匿名。
- **验证码/风控 → `CHALLENGE`**：转人工，绝不尝试绕过。
- **注入安全**：`build_argv` 所有可控值用 `--opt=value` 单 token，URL 前置 `--` 停止选项解析，
  参数数组子进程执行（禁 shell 字符串）。
- **返回元数据脱敏**：`raw_metadata` 递归剔除 `cookie/authorization/token/http_headers` 等键。
- **手工导入始终可用**：`resolve_local_file(path)` → `platform="manual"`（无需下载）。

## 可重放 Job Manifest（README §4）

每次成功下载产出 `AcquisitionManifest`：源 + 提供方 + 工具与锁定版本 + 格式选择 +
输入摘要（`sha256(平台|内容ID|规范URL|格式)`）+ 输出 `sha256`/大小 + 容器 + 时长 + 断点续传开关。
输入摘要可作 Activity Cache Key 一部分（41 §11），逐位可重放。

## 结构

- `runner.py` — `YtDlpRunner` 协议 + `Unconfigured`（默认）/`Subprocess`（真实，args-array）后端。
- `cookies.py` — `CookieResolver` 协议 + `Unconfigured` 默认。
- `connector.py` — `YtDlpDownloadConnector`（`build_argv`/`download`/`probe`/`health_check`）。
- `fixtures/info_dict.json` — 中性合成 info-dict（含机密头以测脱敏），非真实平台响应。
- `tests/` — 契约测试，全程 `FixtureYtDlpRunner`，绝不跑真实二进制。
