# TikTok 发现连接器（source.tiktok）

把 TikTok 的发现信号（关键词/账号/榜单）归一化为 `TrendItemSnapshot`，供 M01 热点情报使用。结构与 `source.douyin` 同构，解析/错误映射/编排复用 `videoforge_provider_sdk` 的发现 kit。

## 三条路径

| 模式 | 状态 | 说明 |
|---|---|---|
| 官方 API（Research/Display） | **未配置**（停止条件） | 需 `tiktok_open_api_client_key/secret` 与 App 审核。未配置返回 `UNCONFIGURED`。 |
| L4 公开信号适配器 | **实时抓取未启用** | 非官方接口（TikTok-Api 等）依赖 Cookie/签名，易变、涉及 ToS/风控。解析层复用 kit 并用录制 fixture 测试；实时 fetcher 未接入，需授权。遇验证码/风控返回 `CHALLENGE` 转人工，不绕过。 |
| 手工导入 | **始终可用** | 用户提供归一化 JSON → snapshots。 |

## 中性采集响应格式

与 douyin 相同的**平台中性**格式（本仓库自有，非 TikTok 私有 API 结构）。缺失指标保留 `null`，绝不填 0。把真实 TikTok 响应转成此格式的适配器就是需要真凭据/授权的部分（未实现）。

## 停止条件（docs/implementation/53 §10）

启用官方或 L4 实时路径需真实凭据/授权；遇验证码/风控必停人工。在此之前，手工导入 + 录制 fixture 是工作路径。
