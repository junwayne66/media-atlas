# P1 Exit 验收报告（趋势情报 + 获取层）

对应 `53-coder-agent-roadmap.md` 的 **P1 Exit** 关口与 `54-mvp-acceptance.md` §2 功能矩阵
的 P1 相关行。所有数字来自 `tests/acceptance/` 的可复跑验收套件（`uv run pytest tests/acceptance -q`），
非人工承诺。

> 结论：**P1 Exit 通过**（含明确标注的停止条件延后项）。全部 P1 实现任务 VF-101…VF-107 完成。

## 1. 出口标准与判定

| 出口标准（53 §P1 Exit） | 判定 | 证据 |
|---|---|---|
| 50 个试点链接可导入 **或** 明确提示人工回退 | ✅ 通过 | 61 条试点链接，**0 静默失败**，100% 明确处置 |
| 热点 Top-20 有证据和可重放得分 | ✅ 通过 | 24 聚类评分，Top-20 各有 reason_codes + sub_scores，逐位可重放 |

## 2. 获取链路（`test_p1_exit_acquisition.py`）

试点集 `pilot_links.py` 为**中性合成样本**（非真实抓取的私有 URL），覆盖抖音/TikTok 的规范链接、
分享文本、短链、`modal_id`/`item_id` 变体、YouTube、不支持域名与本地文件。

**实时下载是停止条件**（53 §10：需真实账号/资源），两个下载 Provider（yt-dlp / f2）默认
`Unconfigured`、不触网，故验证的是「可导入 **或** 明确人工回退」这一 OR 条件——每条链接都落入
一个明确、可诊断的处置：

| 处置 | 数量 | 含义 |
|---|---:|---|
| `resolved_manual_fallback` | 34 | 可识别平台+内容 ID，实时下载未配置 → `DownloadRouter` 明确回退手工导入 |
| `needs_expansion` | 20 | 短链，需先展开（粘贴规范链接或手工导入） |
| `unresolvable_clear_error` | 4 | 不支持域名/非链接 → 明确报错，引导手工导入 |
| `manual` | 3 | 本地文件 → 手工导入始终可用 |
| **silent_fail** | **0** | —— |

- 平台分布：抖音 25 / TikTok 25 / YouTube 4 / 不支持 4 / 本地 3 = **61 条（≥50）**。
- 明确处置率 **100%**，静默失败 **0**——满足「可导入或明确提示人工回退」。
- 回退语义安全（VF-106）：`DownloadRouter` 对 CHALLENGE/AUTH 终止转人工、不跨 Provider 绕过风控。

## 3. 热点 Top-20（`test_p1_exit_trend.py`）

24 个聚类，各含跨平台（抖音+TikTok）多周期快照，用纯 `videoforge_domain.rescore_cluster` 评分：

- Top-20 `hot_score` 区间 **0.5272 .. 0.5685**，**20 个分数各不同**——真实排序而非并列。
- 每条 Top-20 都有 **证据**：`reason_codes`（如 `HIGH_ACCELERATION` / `HIGH_VELOCITY` /
  `CROSS_PLATFORM` / `EARLY_STAGE`）+ `sub_scores`（速度/加速度/跨平台等子分数）+ `weights_version=v1`。
- **逐位可重放**：同输入两次评分 `hot_score` / `sub_scores` / `stage` / `reason_codes` 完全相同。
- 对齐 54 §2「热点」行（多周期跨平台快照 → 速度/加速度/阶段可重放且有理由）与「指标」行
  （缺字段保持 null 不填 0——`TrendItemSnapshot` 指标可空，VF-101）。

## 4. 去重（`test_p1_exit_dedup.py`）

对齐 54 §2「去重」行（同内容不同转码 → 同 duplicate group，来源仍独立）：

- 同内容不同转码（逐帧低汉明扰动）序列相似度 **1.0** → 聚入同一 `duplicate group`（VIDEO 层）。
- **来源仍独立**：`find_duplicate_groups` 不改输入、不删除任何来源记录（只建组 + 相似度）。
- 三层证据（文件 SHA / 视频 pHash / 文本 SimHash）均可建组。
- 真实媒体端到端佐证见 `packages/media-core/tests/test_video_fingerprint.py`：ffmpeg 合成
  testsrc 两种转码（320x240 crf20 vs 480x360 crf32）聚同组、mandelbrot 异内容不聚。

## 5. 已实现 vs Fake vs 延后

| 能力 | 状态 |
|---|---|
| URL 解析（平台/内容 ID/短链/分享文本/手工） | 已实现（VF-105） |
| 下载 Provider（yt-dlp / f2）+ 优先级/回退路由 | 已实现，**实时下载默认未启用**（停止条件；录制 fixture 打桩） |
| 热点评分/阶段/reason codes + 看板/详情 UI | 已实现（VF-101/104） |
| 去重引擎（文件/视频/文本层）+ 真实视频指纹 | 已实现（VF-107） |
| 音频声纹指纹（Chromaprint/fpcalc） | **延后**（本机未装；去重 AUDIO 层已就绪，接入即生效） |
| 断点续传「中途断网恢复不重复 SourceAsset」 | **延后**（依赖实时下载；`--continue`/`--no-overwrites` 已就位，待授权验证） |
| `SourceAsset`/`DuplicateGroup` 持久化 + IngestWorkflow 串联 | **延后**（本阶段为纯引擎 + 连接器机器件，工作流接线在后续） |
| ASR / OCR / Blueprint | 属 **P2**，不在 P1 出口范围 |

## 6. 复跑

```bash
uv run pytest tests/acceptance -q      # 14 项 P1 Exit 验收
uv run pytest -q                       # 全量回归
```
