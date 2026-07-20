# M01：热点发现与选题智能

## 1. 目标

把“榜单上有什么”升级为“现在值得为特定账号做什么”。输出不只是视频列表，而是跨平台事件聚类、趋势阶段、竞争饱和度、内容缺口和可执行创意机会。

## 2. 首期信号

### 2.1 抖音

- 官方开放平台可用的热词/排行/授权账号数据。
- 抖音榜单和关键词/话题页的公开信号适配器。
- 指定对标账号、新发布和互动增量。
- 手动导入链接/CSV，作为连接器失效时的可靠回退。

### 2.2 TikTok

- TikTok Creative Center/公开趋势信号（在允许和可获取范围内）。
- 关键词、Hashtag、音频、指定账号和视频快照。
- TikTok-Api 等非官方连接器只放在 L4 隔离层。
- 手动导入 URL/导出数据回退。

### 2.3 AI/科技辅助种子

MVP 可接 RSS、产品发布博客、GitHub Trending、Hacker News 等作为“事实/关键词种子”，但不能用外部新闻热度替代平台内热度。种子只用于聚类、检索和提前发现。

## 3. 采集模型

### 3.1 Snapshot，而不是覆盖当前值

热点需要速度和加速度，必须保留周期快照：

```text
TrendItemSnapshot:
  observed_at
  platform, region, locale
  item_id, author_id, published_at
  views, likes, comments, shares, saves
  followers_at_observation?
  rank, hashtag_ids[], sound_id?
  raw_artifact_id, collector_version
```

首期建议：热门候选 15 分钟一次；普通监控 1 小时一次；24 小时后逐步降频。

### 3.2 数据标准化

- 数值转为同平台/同地区/同年龄窗口的 robust z-score。
- 对缺失指标保留 `null`，不得填 0。
- 用 `source_confidence` 表示官方、公开页面、浏览器抓取、手工导入的可信度。
- 记录观看数可能被平台延迟更新的事实。

## 4. 聚类

流程：

1. 从标题、字幕、OCR、Hashtag、实体和音频生成多模态文本。
2. 规则归一化产品名、版本号、公司、人名和时间。
3. Embedding 近邻召回。
4. 以事件实体 + 时间窗口 + 语义相似度做层次聚类。
5. LLM 只为边界样本命名/合并，原始证据不被改写。
6. 跨中英文用实体和多语 Embedding 对齐。

聚类必须保留 `member_item_ids` 和合并理由，支持人工拆分/合并。

## 5. 热度评分

所有子分数先映射到 `[0, 1]`：

```text
raw = 0.24 * velocity
    + 0.18 * acceleration
    + 0.14 * engagement_efficiency
    + 0.13 * cross_platform_score
    + 0.12 * topic_fit
    + 0.10 * novelty
    + 0.09 * source_quality
    - 0.15 * saturation
    - 0.12 * decay

hot_score = sigmoid(raw) * source_confidence
```

定义：

- `velocity`：单位时间新增观看/互动，相对同 cohort 标准化。
- `acceleration`：速度斜率，识别正在起飞而非已经很大。
- `engagement_efficiency`：互动/观看，并按账号体量校正。
- `cross_platform_score`：不同平台/账号同步出现。
- `topic_fit`：与 AI/科技/数码频道画像、语言和地区相关性。
- `novelty`：与近 30 日已做选题的距离。
- `source_quality`：原始来源、事实可验证性、素材可得性。
- `saturation`：同质内容数量、头部账号占比、模板重复度。
- `decay`：距峰值时间和速度转负程度。

权重是模板版本，必须通过历史表现校准，不写死在代码。

## 6. 趋势阶段

```text
EMERGING -> RISING -> PEAK -> SATURATED -> DECAYING -> ARCHIVED
```

- `EMERGING`：样本少但加速度高。
- `RISING`：速度/跨平台增长持续。
- `PEAK`：绝对热度高、加速度接近零。
- `SATURATED`：同质供给快速增加。
- `DECAYING`：速度为负或搜索/互动显著回落。

状态变化产出事件，触发选题/停止自动生成，而不是每次全量扫描。

## 7. Creative Opportunity

```json
{
  "trend_cluster_id": "trc_...",
  "angle": "用 45 秒解释新模型对普通 Mac 用户的实际影响",
  "target_audience": "关注 AI 工具的中文创作者",
  "recommended_language_variants": ["zh-CN", "en-US"],
  "recommended_creation_modes": ["STRUCTURE_REWRITE", "SOURCE_REEDIT"],
  "evidence_item_ids": ["tri_1", "tri_2"],
  "content_gap": "现有热门视频多报参数，缺少实测成本与限制",
  "urgency": 0.86,
  "confidence": 0.74,
  "reason_codes": ["HIGH_ACCELERATION", "CROSS_PLATFORM", "LOW_EXPLAINER_SUPPLY"]
}
```

## 8. API

- `POST /v1/trend-collectors/run`
- `GET /v1/trend-clusters?stage=RISING&vertical=ai-tech`
- `GET /v1/trend-clusters/{id}`
- `POST /v1/trend-clusters/{id}/merge`
- `POST /v1/trend-clusters/{id}/split`
- `POST /v1/trend-clusters/{id}/opportunities:generate`
- `POST /v1/opportunities/{id}/projects`

## 9. 连接器可靠性

每个平台采集能力维护独立 SLO：

- 最近 24h 成功率。
- 返回结构 Schema 漂移。
- 样本数量异常。
- 快照关键字段缺失率。
- HTTP/风控/登录错误分类。
- 金丝雀关键词/账号的预期最小结果。

连续失败后熔断，UI 标红并允许手动导入；不得悄悄返回空榜单。

## 10. 验收

- 同一原事件的中英文/跨平台样本可聚为一组，试点准确率 ≥ 80%。
- 热度计算可重放；给定快照和权重得到完全相同结果。
- 每个 Top-20 结果有至少 2 个 reason codes 和来源证据。
- 连接器空结果能区分“真的无数据”和“采集失败”。
- 人工拆分/合并后不会被下一轮无条件覆盖。

