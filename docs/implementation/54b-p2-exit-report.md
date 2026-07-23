# P2 Exit 验收报告（理解与 Blueprint）

对应 `53-coder-agent-roadmap.md` 的 **P2 Exit** 关口与 `54-mvp-acceptance.md` §2 功能矩阵的
P2 相关行。所有数字来自 `tests/acceptance/` 的可复跑验收套件（已接入 pytest `testpaths`，
`make test` 强制执行），非人工承诺。

> 结论：**P2 Exit 通过**（含明确标注的停止条件延后项）。全部 P2 任务 VF-201…VF-205 完成。

## 1. 出口标准与判定

| 出口标准（53 §P2 Exit） | 判定 | 证据 |
|---|---|---|
| 20 条中英样本 Blueprint 可追溯到证据 | ✅ 通过 | 22 样本，**22/22 校验零 issue、22 个 Claim 全部可回跳真实证据** |
| 局部 Provider 重跑不重复下载 | ✅ 通过 | Activity Cache Key 命中不重算；换输入/模型/配置即重算 |

## 2. Blueprint 可追溯（`test_p2_exit_blueprint_traceability.py`）

样本集 `p2_samples.py` 为**中性合成样本**（非真实媒体），覆盖中/英/混语，含低置信、说话人切换、
字幕/水印文本轨、视觉帧、不同时长：

| 语言 | 数量 |
|---|---:|
| 中文 zh-CN | 8 |
| 英文 en-US | 8 |
| 混语（段内切换） | 6 |
| **合计** | **22（≥20）** |

每条样本走 P2 全链路（Fake 串联）：`transcript`(ASR) + `text_tracks`(OCR) + `visual_analysis`(VLM)
→ `domain.build_candidate_rhetorical_beats`（程序提供候选时间范围）+ `build_visual_beats`
→ `FakeBlueprintFusionProvider` 融合 → `VideoBlueprint`。逐条断言：

- **校验护栏零 issue**：`validate_blueprint` 对全部 22 条返回 `[]`（时间单调/在时长内、Claim 有非空
  证据、覆盖率并集 ≥0.9）——**22/22 通过，总 issue 数 0**。
- **每 Claim 可回跳真实证据**：22 个 Claim 的 `evidence.ref_id` 全部解析到真实 transcript 段或
  文本轨 id——**22/22 可追溯**。
- **节拍时间来自程序候选**：每个 rhetorical 节拍的 `(start,end)` 都属于候选集合，**LLM/Fake 未编造
  时间戳**；且在 `[0,duration]` 内。
- **节拍 claim_ids 可解析**：所有 `beat.claim_ids` 引用真实 Claim。
- 对齐 54 §2「Blueprint」行（Claim/Beat 都有证据时间点）、「ASR」行（词级时间/语言/低置信标记，
  见 Transcript 合同 + `mark_low_confidence`）、「OCR」行（稳定 TextTrack，见 `track_text_observations`）。

## 3. 局部重跑不重复下载（`test_p2_exit_cache_rerun.py`）

对齐 54 §2 缓存/局部重跑（41 §11）：`activity_cache_key = sha256(input_digest + provider +
model_version + normalized_config + schema_version)`。用它把计数 Provider 包成 `CachedStage`：

- **同输入 + 同 provider + 同模型 + 同配置** → 缓存命中，底层只执行一次（`calls == 1`）——
  局部重跑**不重复下载/计算**。
- 改**配置** / 改**模型版本** / 改**输入** 任一 → 缓存键不同、未命中、重算（`calls == 2`）。
- 配置键序无关（规范化）→ 语义相同的配置命中同一缓存。
- 据此「换字幕不重跑下载/镜头、换 OCR 模型只重跑 OCR」（§11）由缓存键区分。

## 4. 已实现 vs Fake vs 延后

| 能力 | 状态 |
|---|---|
| 媒体运行时（probe/proxy/audio/scene）+ 可重放 Job Manifest + Cache Key | 已实现（VF-201，真实 ffmpeg） |
| 统一词级 Transcript 合同 + 低置信标记 + ASR 端口/路由 | 已实现，**真实 ASR 引擎延后**（需模型；Fake 回放） |
| TextTrack 合同 + 跟踪/多帧投票/分类 + OCR 端口 | 已实现，**真实 OCR 引擎延后**（Fake 回放） |
| VisualAnalysis 合同 + 代表帧选择（封顶禁逐帧）+ VLM 端口 | 已实现，**真实 VLM 延后**（Fake 回放） |
| VideoBlueprint 合同 + 候选/校验护栏 + 融合端口 | 已实现，**真实 LLM 融合延后**（Fake 装配通过校验的蓝图） |
| 音频声纹指纹 / 说话人分离模型 / 光流跟踪精化 | **延后**（需模型/工具） |
| AnalysisWorkflow：持久化四合同 + 缓存键局部重跑接线 | **延后**（本阶段为合同 + 纯域 + Provider 端口/Fake 机器件） |

## 5. 复跑

```bash
uv run pytest tests/acceptance -q      # P1 + P2 Exit 验收
uv run pytest -q                       # 全量回归
```
