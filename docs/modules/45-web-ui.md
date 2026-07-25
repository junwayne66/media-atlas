# M-Web:前端功能模块需求(交付 UI 工程师)

> 本文是 Web 控制台的**功能模块需求**与 API 映射,交付 UI 工程师做视觉/交互设计并实施。本文只约束功能、数据与交互语义,不规定视觉方案;§0.2 的交互红线与 §0.3 的非视觉约束是设计必须满足的硬需求。
> 技术栈约束(ADR 既定):Vue 3 + TypeScript strict + Vite;UI **只**依赖生成的 `@videoforge/contracts`(contracts-ts)类型与控制面 REST API,绝不依赖后端内部实现或第三方平台细节。开发期 `/api` 前缀反代到 `:8000`。

## 0. 全局框架

### 0.1 导航壳

左侧固定侧边栏 + 顶部工具条:

| 导航项 | 模块 | 优先级 |
| --- | --- | --- |
| 热点池 | M-W1 | P0(已有,增强) |
| 素材库 | M-W2 | P0 |
| 项目 | M-W3 / M-W4 / M-W5 / M-W6 | P0(工作台)→ P1(编辑深化) |
| 审核 | M-W7 | P1 |
| 发布 | M-W8 | P1 |
| 效果 | M-W9 | P2 |
| 设置 | M-W10 | P2 |

顶部工具条:API 健康徽章(`GET /healthz`)、全局搜索(P2)、暗色模式切换、当前账号(P2)。

### 0.2 全局交互红线(由后端合同派生,UI 必须遵守)

1. **空态 ≠ 错误态 ≠ 未配置态**。所有列表/看板必须区分三态:`EMPTY`(拉过了,确实没有)、`FAILED`(拉取失败,展示错误原因)、`UNCONFIGURED`(能力未配置,引导去设置)。绝不出现"静默空看板"。
2. **null ≠ 0**。指标字段为 null 表示"未采到",渲染为 `—`(带 tooltip"未采集"),绝不渲染成 0 或参与前端聚合运算。
3. **乐观锁冲突不静默**。所有写操作携带 `expected_version`;409 时提示"数据已被他人修改",展示冲突信息并重新加载,绝不自动覆盖。
4. **FATAL 不可覆盖**。审核/QA 中 FATAL/BLOCKER 级问题没有"强制通过"按钮;MAJOR 类按策略展示可覆盖入口。
5. **挑战只能转人工**。登录失效/验证码/风控等 `WAITING_FOR_HUMAN` 状态只提供"去人工处理"指引,UI 不提供任何绕过或自动重试入口。
6. **样本不足不排序**。效果看板中 `enough_samples=false` 的分组进"样本不足"区,不参与排序展示。
7. **关联非因果**。学习信号文案永远用"相关/关联",禁用"导致/提升了"表述(后端 `association_only` 恒 true)。
8. **审批绑定内容**。实体版本或内容变化后,旧审批展示为"已失效",需重新审批。
9. 长任务展示遵循 Task Lease 语义:状态轮询 + 可重试(幂等),终态 FAILED 可人工 requeue。

### 0.3 给设计的非视觉约束(硬需求,不限定视觉方案)

- **状态语义全站一致**:「等人工 / WAITING_FOR_HUMAN」「阻断 / BLOCKER·FATAL」「成功」「警告」四类状态各自需要一个全站唯一、可即时辨认的视觉语义(具体色彩/形态由设计定);状态不得只靠颜色区分,必须伴随文字或图标(可达性)。
- **数据密度**:本产品是运营驾驶舱,以表格/列表为主;ID、哈希、时间码、指标等数据建议等宽字体 + 列对齐(`tabular-nums`)。
- **暗色模式**:必须支持深浅两套主题(macOS 试点用户习惯),非机械反色。
- **中文优先**:界面主语言简体中文,预留 i18n;文案措辞遵守 §0.2 红线(如"对账"不叫"重试","相关"不叫"导致")。
- **键盘可达**:所有可交互元素有可见焦点态;动效尊重 `prefers-reduced-motion`。

## 1. M-W1 热点池(增强)

现状:已有 TrendBoard/TrendDetail 垂直切片(列表、阶段/理由码徽章、子分数、重算、拆分、合并、一键建项目)。

增强需求:

- 趋势曲线:snapshot 序列的 views/likes 随时间小图(sparkline),detail 内放大图。
- 合并操作 UI(现仅 API):选择源簇 → 确认(展示 MERGED_FROM/MERGED_INTO 出处)。
- 阶段筛选记忆化、按 vertical 的 tab 快捷分组。
- 一键建项目后跳转项目工作台。

API:`/v1/trend-clusters` 全族(已有)。数据合同:`TrendCluster`、`TrendItemSnapshot`、`TrendSubScores`。

## 2. M-W2 素材库 / 采集

目标:把"链接 → 可分析素材"的入口做成产品。**live 下载未接通(stop-condition),UI 必须诚实展示 manual fallback 处置,不假装在下载。**

用户流程:

1. 粘贴 URL/分享文本 → `POST /v1/sources:resolve` 预览解析结果(平台、content_id、canonical_url、是否需短链展开、不可解析原因)。
2. 确认导入 → `POST /v1/sources/import-url` 持久化 SourceAsset,展示处置:`MANUAL_FALLBACK`(引导人工下载后关联文件)/ `NEEDS_EXPANSION` / `UNRESOLVABLE`(清晰错误)。
3. 本地文件导入 → `POST /v1/sources/import-file`(macOS 试点:文件路径)。
4. 素材列表:平台、状态、指纹、时长、关联项目;详情页含 AcquisitionManifest(工具版本、哈希——可复现性证据)。
5. 重复组:`GET /v1/sources/duplicate-groups` 展示按 FILE/VIDEO/AUDIO/TEXT 层聚出的重复组;**只展示分组证据,绝无删除源记录操作**(合同红线)。

状态:每个 SourceAsset 的 disposition + download status 徽章;CHALLENGE → 人工指引。

## 3. M-W3 项目工作台

目标:一个项目 = 一条"趋势 → 成片 → 发布 → 效果"流水线的驾驶舱。

- 项目列表:标题、来源趋势簇、创作模式(STRUCTURE_REWRITE/SOURCE_REEDIT)、语言对、状态、更新时间。
- 项目详情首屏 = **流水线阶段图**:采集 → 分析 → 创作 → 本地化 → QA → 审核 → 发布 → 效果,每阶段状态(未开始/进行中/完成/需人工/失败)可点进对应模块。
- 阶段状态来自各域对象的存在性与状态字段(见各模块 API);"需人工"聚合所有 `WAITING_FOR_HUMAN` / needs_review 项为待办清单。

API:`GET /v1/projects`、`GET /v1/projects/{id}`(本轮新增)+ 各模块状态端点。

## 4. M-W4 分析查看器(Blueprint Viewer)

目标:AI 分析产物的可视化与可追溯展示。当前引擎为 Fake(录制 fixtures),UI 按真数据结构开发,引擎替换不改 UI。

- 转写视图:分段 + 逐词时间戳,低置信词/段高亮(`low_confidence`),混合语言分段标签。
- 画面文字轨:TextTrack 列表(kind 徽章:CAPTION/TITLE/BRAND_MARK…),时间跨度条,投票文本与观测轨迹展开。
- 视觉分析:采样帧列表(采样理由徽章:SCENE_CUT/TEXT_CHANGE/PERIODIC…),caption 为 null 显示"未分析"(诚实,不编造)。
- **Blueprint 视图(核心)**:节拍时间轴(rhetorical/visual beats)+ Claim 表。每个 Claim 展示 `source_status`(VERIFIED/UNVERIFIED/**DISPUTED** 红色)与证据链(点击跳转到对应转写段/文字轨)。`validate_blueprint` 的 issue 列表直接展示。
- 缓存证据:每阶段展示 cache_key 与"命中缓存/重新计算"标记(重跑按钮语义 = 同 key 命中即秒回)。

API(本轮新增):`POST /v1/projects/{id}/analysis:run`、`GET /v1/projects/{id}/analysis`(各阶段状态 + 产物 id)、`GET /v1/projects/{id}/analysis/transcript|text-tracks|visual|blueprint`。

## 5. M-W5 创作编辑

目标:两种创作模式的产物查看与生成动作(编辑深化 P1/P2 迭代)。

- Brief 视图:目标/受众/角度/Hook/must_cover(引用 Claim 表,DISPUTED 的不可选——后端护栏拒绝,UI 前置禁用)+ VisualMix 饼比。
- 脚本版本:ScriptVersion 列表(v1/v2…),句子级展示(角色、目标时长、引用 claim 徽章);`validate_script` issue(反抄袭/时长/禁词/覆盖)内联标注。动作:`POST /v1/projects/{id}/scripts:generate`(Fake 结构改写)。
- 高光候选(SOURCE_REEDIT):窗口列表 + 11 维子分数雷达/条形 + 理由码;Top-N 与人工标注(P2)。
- 重剪计划:EditOp 序列(KEEP/DELETE/MUTE/SPEED)时间轴显示 + 连续性提示(JUMPCUT_SMOOTH…)。
- 时间线:轨道视图(V0–V5 / A0–A3 / M0),Segment 的九个扩展字段做溯源侧栏(source_ref → script_sentence → template_slot → asset);`validate_timeline` issue 展示。动作:`POST /v1/projects/{id}/timeline:compile` 返回 RenderManifest 预览(argv/filter graph 折叠展示 + cache key)。
- QA 报告:findings 按严重级分组(BLOCKER 红/MAJOR 橙/MINOR/INFO),时间点可跳转;`pass_or_block` 大徽章。

API(本轮新增):brief/scripts/timeline/qa 端点族,详见 §11 映射表。

## 6. M-W6 本地化工作台

目标:§13 句级批准 + 局部重跑的操作台。

- 变体列表:每目标语言一个 LocalizationVariant,QA 汇总徽章。
- **句级并排编辑器(核心)**:左 Canonical(含 must_keep_terms 高亮),右译文;每句显示 QA findings(数字/专名/否定一致性,BLOCKER 红)、TTS 时长拟合状态(方法徽章:TTS_SPEED/LLM_REWRITE…,NEEDS_REVIEW 橙)、口型状态(方法 + 自动降级警告)。
- 动作:批准/驳回/编辑(EDITED 必须带 edited_text——合同硬拦);编辑保存后展示**重跑作用域预览**(`compute_rerun_scope`:只该句 TTS/字幕/口型 + 全局混音/渲染一次),用户确认后触发。
- 字幕预览:cue 列表 + 阅读速度(CPS/WPM)标尺,超速红标;SRT/ASS 导出下载。
- 发布门:`validate_localization_publish_gate` 结果 + APPROVED_OVER_BLOCKER 护栏(带 BLOCKER 的句子批准按钮禁用)。

API:P2 迭代接入(域层已就绪,持久化端点随本地化 workflow 落地补齐——需求先行,UI 可用 mock 数据开发此模块)。

## 7. M-W7 审核中心

- 审核队列:按策略(ALWAYS/NEW_TEMPLATE_ONLY/AUTO)过滤的待审实体;严重级门禁展示(FATAL → 阻断,不可覆盖)。
- 审核详情:实体快照 + QC 报告 + 版本/内容摘要;决定动作(APPROVED/REJECTED + scope)。
- **审批有效性**:实体后续变化 → 原审批标记"已失效"(修改失效红线),入口重审。
- 模板信任:NEW→TRUSTED 状态机可视化(七条升级准则达标情况),关键字段变更 → 回退 NEW 的历史记录。

API(本轮新增):`POST /v1/review-decisions`、`GET /v1/review-decisions?entity_id=`、`POST /v1/review-decisions/{id}/validate`。

## 8. M-W8 发布

- 预检:`POST /v1/publish-jobs/{job_id}/preflight` 展示 PreflightReport(16 检查项分组:媒体/元数据/授权/账号;ERROR/FATAL 阻断,WARNING 提示"可见性受限");方法阶梯展示(官方 API → 分享 SDK → 浏览器 → 真机 → 手工导出,当前可用项高亮——**均为 Fake/未配置,UI 明示**)。**请求体只传媒体探针**:元数据一律以建任务时入库的那份为准(它参与幂等键、建好后不可变),所以预检展示的输入与提交判定的输入永远是同一份;要换元数据就建新任务(键自然不同)。旧式带 `metadata` 的请求体会被 422 拒。
- 发布 Job 列表/详情:状态机可视化(PENDING→UPLOADING→SUBMITTED→…);attempts 时间线(request_digest、external token——幂等对账证据);动作:submit(仅 UPLOADING 且未提交时可用)、reconcile(对账,绝不盲目重发)、manual-complete(WAITING_FOR_HUMAN → 人工回填 external_id)。**"重试"按钮的语义是对账而非重发**,文案必须写清。
- 发布日历:publishing_window 配置(支持跨零点)、next_publish_time 预览、副本(copy_index)语义提示(副本=新 Job,同内容=去重)。
- 挑战面板:所有 WAITING_FOR_HUMAN Job 聚合,展示挑战类型(登录/验证码/设备/内容警告)与人工处理指引。

API(本轮新增):`/v1/publish-jobs` 全族 + preflight + calendar 预览。

## 9. M-W9 效果看板

- 快照采集:计划(1/3/6/24/72h/7d)完成度环;缺失指标显示 `—`。
- 账号内相对看板:按 age+metric 视角,分组维度(模板/Hook/创作模式/时长桶/语言/时段)的相对中位数条形图;**enough_samples=false 分组进"样本不足"折叠区,不排序**。
- 学习信号:信号 × 结局的 Spearman 相关卡片(方向徽章 POSITIVE/NEGATIVE/NONE/INSUFFICIENT),文案模板:"X 与 Y 相关(非因果)"。
- 排序器校准:当前 vs 候选权重对比、离线评估(秩相关/Top-k 命中)、决策徽章(KEEP_CURRENT/EXPLORE≤20% 探索流量/INSUFFICIENT_SAMPLES)——**无"全量上线"按钮,这是合同红线**。

API(本轮新增):`/v1/performance/*` 只读端点族。

## 10. M-W10 系统与设置

- Provider 注册表:连接器列表(能力、kill-switch、熔断器状态、统计)。
- Worker 队列:workers 心跳、worker_tasks 状态(含终态 FAILED + 人工 requeue 按钮)。
- 账号:PlatformAccount(**无任何明文凭据展示**——credential_ref 只显示 handle 摘要)、绑定方式、发布窗口。
- 第三方清单:third_party_manifest 只读展示(许可隔离级 L0–L4)。

API:workers 路由(已有 + requeue 新增);其余 P2。

## 11. API 端点映射总表

| 端点 | 方法 | 状态 | 模块 |
| --- | --- | --- | --- |
| /healthz | GET | ✅ 已有 | 全局 |
| /v1/trend-clusters 全族 | * | ✅ 已有 | M-W1 |
| /v1/operations | POST | ✅ 已有 | 全局(幂等操作入口) |
| workers 注册/心跳/claim/renew/complete/fail | * | ✅ 已有 | M-W10 |
| worker-tasks requeue(终态 FAILED 人工恢复) | POST | ✅ 已有 | M-W10 |
| /v1/sources:resolve | POST | ✅ 已有 | M-W2 |
| /v1/sources/import-url · import-file(幂等;不存在的 project → 404) | POST | ✅ 已有 | M-W2 |
| /v1/sources · /{id} · /duplicate-groups(FILE 层) | GET | ✅ 已有 | M-W2 |
| /v1/projects · /{id} | GET | ✅ 已有 | M-W3 |
| /v1/projects/{id}/analysis:run(阶段级 cache_hit 可见;无本地文件素材 → 409) | POST | ✅ 已有 | M-W4 |
| /v1/projects/{id}/analysis(+ transcript/text-tracks/visual/blueprint) | GET | ✅ 已有 | M-W4 |
| /v1/projects/{id}/brief:generate · scripts:generate · timeline · timeline:compile | POST | ✅ 已有 | M-W5 |
| /v1/projects/{id}/brief · claim-table · scripts(含 status/issues)· timeline · render-manifests | GET | ✅ 已有 | M-W5 |
| /v1/review-decisions(+ validate) | * | ✅ 已有 | M-W7 |
| /v1/publish-jobs 全族(+ preflight/submit/reconcile/manual-complete) | * | ✅ 已有 | M-W8 |
| /v1/publish-calendar/next | GET | ✅ 已有 | M-W8 |
| /v1/performance/snapshots:capture · snapshots · dashboard · learning-report | * | ✅ 已有 | M-W9 |
| QA 报告端点(随 QA 工作流落地) | GET | 📋 计划 | M-W5 |
| 本地化工作台端点族 | * | 📋 计划 | M-W6 |
| Provider 注册表/账号管理端点 | * | 📋 计划 | M-W10 |

> ✅ 已有 = 后端已落库并有集成测试(引擎与发布执行均为 Fake,UI 需明示);📋 计划项先按 contracts-ts 合同类型 mock。两个实现细节 UI 需知:① `scripts:generate` 并发撞版本号时可能返回 409「产物版本冲突,请重试」——UI 做自动重试或提示;② 发布 Job 详情里的 `preflight_report` 列是展示用历史报告,提交时仍以服务端**实时重跑**的预检为准;submit 被拦时会**同步落库** PREFLIGHT_BLOCKED 状态 + 那份新的失败报告(列不再滞后),UI 直接读 `PublishJobView.preflight_report` 即可展示"为什么被拦"。

> **工程收编状态**:控制台已从独立 npm 项目 `media-atlas-app/` 收编为 pnpm workspace 成员 `apps/console`(`@videoforge/console`),并已把领域对象类型接到生成的 `@videoforge/contracts` 上——`src/api/*.ts` 里原先手写的 TrendCluster / SourceAsset / Project / Transcript / TextTrackSet / VisualAnalysis / VideoBlueprint / ScriptVersion / CreativeBrief / PublishJob / PreflightReport / ReviewDecision / PerformanceSnapshot / PerformanceDashboard / LearningReport 等**全部改为 `import type` 自合同包**(纯类型,运行时零依赖,不进 bundle);只有端点自有的请求/响应包装(resolve 预览、analysis run 视图、dashboard/learning 包装、DocumentView 等**非注册合同**的形状)保留本地声明。容器镜像 `infra/docker/console.Dockerfile` 同步改为 workspace 构建(`--filter @videoforge/console...`)。

## 12. 分期建议

- **一期(P0)**:导航壳 + 视觉方案落地(UI 工程师产出设计系统);M-W1 增强;M-W2 素材库;M-W3 项目工作台(流水线图)。
- **二期(P1)**:M-W4 Blueprint Viewer;M-W5 创作(脚本/时间线/QA);M-W7 审核;M-W8 发布。
- **三期(P2)**:M-W6 本地化工作台;M-W9 效果看板;M-W10 设置;全局搜索、多账号。

## 13. 验收要点(给 UI 的 DoD)

- 全部界面通过 contracts-ts 类型编译(TS strict,无 any 透传)。**✅ 已成立**:`apps/console` 已在 pnpm workspace 内,领域类型来自 `@videoforge/contracts`,`corepack pnpm -r typecheck` 与 `--filter @videoforge/console build`(vue-tsc strict + vite build)均零错。
- §0.2 九条交互红线逐条可演示。
- 空态/错误态/未配置态三态在每个列表模块可截图验收。
- 409 冲突路径有 e2e 用例(Playwright)。
- 暗色模式全覆盖;中文为主语言,预留 i18n。
