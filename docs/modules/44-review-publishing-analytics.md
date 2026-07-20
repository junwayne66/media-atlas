# M09–M12：质量、审核、发布与反馈

## 1. Review Center

### 1.1 界面

- 低清代理 Player + 帧精确跳转。
- Script/字幕/画面文字/配音句子列表。
- Timeline 简化轨道视图。
- QA 问题 Marker 和前后帧。
- 原版、结构重写版、重剪版、语言变体并排。
- 版本 Diff：文字、素材、切点、Provider、成本、QA。
- 批准、驳回、批注、局部重跑。

### 1.2 ReviewDecision

```json
{
  "decision": "APPROVED",
  "scope": "variant",
  "entity_id": "var_123",
  "entity_version": 7,
  "reviewer_id": "usr_1",
  "policy_snapshot_id": "pol_2",
  "qc_report_ids": ["qc_9"],
  "created_at": "...",
  "signature": "..."
}
```

任何被批准对象修改后，旧批准自动失效。

## 2. QA 严重级别

- `INFO`：不阻塞。
- `WARNING`：按模板/账号策略决定。
- `ERROR`：阻止发布，可人工修复后重跑。
- `FATAL`：媒体损坏、时间线非法、发布目标不确定等，不允许覆盖。

每项包含时间点、证据截图/音频、检测器版本和修复建议。

## 3. 发布连接器优先级

```text
OFFICIAL_API -> OFFICIAL_SHARE_SDK -> BROWSER_AUTOMATION
             -> ANDROID_DEVICE -> MANUAL_EXPORT
```

选择取决于账号、应用审核、平台能力和用户配置。Connector 返回能力，不由 UI 猜测。

### 3.1 TikTok

- 首选 Content Posting API Direct Post。
- 未审核客户端发布可受可见性限制；连接器预检必须展示当前授权/审核状态。
- 查询 Creator Info，按官方可选项生成发布表单。
- 初始化上传、上传媒体、查询状态/Webhook。
- 若官方 API 不可用，浏览器或 Android 适配器进入人审加强模式。

### 3.2 抖音

- 首选抖音开放平台内容发布 OpenAPI。
- 可选抖音分享 SDK，跳转编辑页/发布页由用户完成或真机流程继续。
- 连接器预检文件大小、格式、时长、授权和账号状态。
- 官方数据 API 回收授权账号视频表现。

## 4. PublishWorkflow

1. `FreezeVariant`：锁定 Render、标题、说明、Hashtag、封面和策略快照。
2. `PlatformPreflight`：编码/时长/大小/安全区/账号/权限。
3. `ResolveConnector`：选择官方/浏览器/真机/手工。
4. `WaitUntilSchedule`：Temporal Timer。
5. `EnsureAuthorization`：刷新 Token；失败等待人工。
6. `InitializeUpload`。
7. `UploadMedia`：可恢复/分片时使用平台能力。
8. `SubmitPost`。
9. `VerifyStatus`：Webhook + 轮询。
10. `VerifyExternalPost`：保存外部 ID/URL/内容指纹。
11. `Emit PublishStatusChanged`。

## 5. 幂等与未知状态

`idempotency_key = sha256(account + platform + render_digest + metadata_digest + scheduled_window)`。

- 本地先创建唯一 PublishJob。
- 每次平台调用保存请求摘要和外部 upload/post token。
- 网络超时后先查状态/账号最近帖子，不能直接重发。
- 发现匹配外部帖子后标记 `SUCCEEDED_RECONCILED`。
- 用户明确选择“发布副本”才创建新幂等键。

## 6. 浏览器自动化 Adapter

- Playwright 持久浏览器 Profile，每个账号隔离。
- 选择器优先使用 role/label/test-id，坐标只做最后回退。
- 上传前检查当前账号和目标域名。
- 每个关键步骤截图/DOM 摘要。
- 只在发布连接器白名单域名工作。
- 登录失效、验证码、设备确认、内容警告均进入 `WAITING_FOR_HUMAN`。
- 页面结构契约测试每日运行；失败自动禁用 Connector。

## 7. Android 真机 Adapter

### 7.1 组成

- Appium + UiAutomator2 Driver 为主。
- `openatx/uiautomator2` 用于轻量诊断/辅助。
- ADB 负责设备发现、文件传输、包版本和日志。
- 设备屏幕流/截图进入 Review Center。

### 7.2 流程

1. 绑定已登记设备和账号。
2. 检查电量、存储、网络、解锁、App 版本和前台账号。
3. 通过 ADB 推送已批准视频到隔离相册目录。
4. 优先调用官方 Share Intent/SDK；否则打开 App 发布流。
5. 根据 accessibility selector 选择视频、填文案、封面和选项。
6. 提交前截图 + 元数据摘要；按策略请求最终确认。
7. 提交、等待结果、回到主页查验。
8. 清理临时媒体，保留发布证据。

单设备同一时间只运行一个发布 Job。App 版本更新需要 Canary Device 先通过脚本回归。

## 8. 账号与 Secret

`PlatformAccount` 不含 Secret：

```text
id, platform, display_name, external_account_id
credential_ref, connector_preferences[]
review_policy_id, publishing_window, locale
status, last_verified_at, device_binding_id?
```

- OAuth Refresh Token 服务端加密。
- 浏览器 Cookie/Android 账号会话默认留在 Desktop/Device。
- 控制中心只保存 Credential Handle 和健康状态。
- 所有发布操作写 AuditEvent。

## 9. 发布元数据生成

- 标题/说明/Hashtag 从 Canonical Topic 生成平台变体。
- 每个字段有长度、禁用字符、语言、敏感词和模板规则。
- 标签同时考虑相关性、饱和度和账号历史，不堆砌热门词。
- 封面从高质量帧或模板生成；在不同安全区预览。
- 元数据在批准后冻结，发布 Adapter 不得自行改文案。

## 10. Performance Snapshot

```text
observed_at, platform_post_id, age_hours
views, watch_time, avg_watch_time, completion_rate
likes, comments, shares, saves, follows
impressions?, click_through?, source_confidence
```

只保存平台实际提供的指标，缺失保持 null。建议快照：发布后 1h、3h、6h、24h、72h、7d，按平台限流调整。

## 11. 归因与学习信号

特征：

- TrendCluster、阶段和发布延迟。
- Hook/Beat Template、创建模式、时长、语言。
- 素材类型比例、镜头密度、字幕风格、TTS/声音、音乐。
- QA 警告、人工修改次数。
- 账号、平台、发布时间和历史基线。

目标使用账号内相对指标，例如 `views_at_24h / account_median_24h`，避免跨账号直接比较绝对播放。

首期只做可解释统计和分桶，不直接训练黑盒“爆款模型”。有足够样本后再做排序/多臂老虎机，并保留探索流量。

## 12. 自动化升级条件

模板从 `NEW` → `TRUSTED`：

- 至少 20 个已批准 Render。
- 最近 20 个无 FATAL，ERROR 率低于阈值。
- 语言/平台 QA 均达标。
- 发布成功率和重复发布为 0 问题。
- 内容负责人明确批准模板版本。

模板变更超过字幕样式、Beat、Provider 或发布元数据等关键字段时回到 `NEW`。

## 13. 验收

- 任一版本修改会使旧审批失效。
- 同 PublishJob 反复重试不会重复发布。
- TikTok/抖音官方 API 可用时完成上传、状态查询和外部 ID 保存。
- 浏览器/真机遇到挑战会暂停并通知，不继续盲点。
- 发布前后均能确认当前账号。
- 1/3/6/24/72 小时指标可按计划进入快照，缺失字段不填 0。
- 模板自动发布启用/撤销有完整审计。

