# P4 Exit 验收报告（本地化）

对照 `docs/modules/43-localization.md §13` 六条验收标准，用 VF-401..VF-407 的 domain +
Fake Provider 在 `tests/acceptance/` 跑 20 条中英 AI/科技样本（共 40 句忠实译对）。

跑法：`uv run pytest tests/acceptance/test_p4_exit_*.py -q`（已并入 pytest `testpaths`，
`make test` 强制执行）。

## 样本

`tests/acceptance/p4_samples.py`：20 样本（10 条 zh→en + 10 条 en→zh，AI/非-AI 各半），
每样本 2 句忠实译对，**刻意含数字、产品名、否定**以证明检查非空跑。数字保留为数字、
verbatim 产品名（M5/H100/Llama 3/Claude/OpenAI/Google/Meta…）在译文中保留、否定标记
一一对应；被本地化的公司名（Tesla→特斯拉、Nvidia→英伟达）按 VF-401 术语表语义处理，
不作为 verbatim 保留项。

## 覆盖

### ① 数字/产品名/否定一致率 100% —— ✅
`test_p4_exit_consistency.py`：40 句经 `run_consistency_checks`（数字多重集 + 否定标记数，
纯 domain）+ `FakeLocalizationConsistencyProvider`（浅层专名保留）→ **零发现**，发布门
`aggregate_localization_qa` 放行。**非空跑护栏**：从每个含数字句删数字必被
`NUMBER_CONSISTENCY` BLOCKER 抓（≥15 句）；从含专名句删专名必被 MAJOR 抓（≥5 句）——
证明检查真的在跑，不是空断言。

### ② 字幕 100% 通过安全区与阅读速度 —— ✅
`test_p4_exit_subtitle.py`：每句译文经 VF-402 `pack_lines_into_cue` 分行合成 cue，
`validate_subtitle_track` **零违规**（行长/CPS/重叠/时长/语言）；安全区由模板
`SafeAreaSpec`（5/95/5/90 pct，覆盖抖音/TikTok 底部 UI）结构性保证。**非空跑护栏**：
把一条 cue 压到 600ms → CPS 爆表 → 必被 `READING_SPEED_EXCEEDED` 抓。

### ⑤ 口型失败自动降级、不阻塞 Workflow —— ✅
`test_p4_exit_lipsync_nonblocking.py`：40 句构造口型片段（循环覆盖 合格通过/合格QA失败/
不合格/意图 四情形），`plan_lipsync` → `validate_lipsync_plan` **恒为空**；每片段都有具体
非阻塞 method，QA 未过绝不停在 GPU_SYNTHESIS。极端场景：**全部合成失败 + 无回退资源** →
全部落到 `KEEP_UNSYNCED` 终局并置 `needs_review`（形成警告），计划仍成立。OFF 模式全部
保留非口型配音。

### ⑥ 改单句译文只重跑该句 TTS/字幕/口型 + 下游 —— ✅
`test_p4_exit_local_rerun.py`：在 40 句全量变体上，`compute_rerun_scope` 编辑任意一句 →
只该句进 `(TTS, SUBTITLE, LIPSYNC)`，其余 39 句进 `unaffected_sentence_ids` 且**零阶段**，
全局 `(AUDIO_MIX, RENDER)` 一次；`TRANSLATION` 绝不进重跑集（改译文本身是输入）。分区性质
（per_sentence 键 == 编辑集、unaffected == 全集 − 编辑集、并集覆盖全集）在任意子集上成立。

## 诚实登记（部分覆盖 / 延后）

### ③ 高置信目标文字未翻译率 < 2% —— 🔸 护栏已在，端到端未单列
VF-403 `decide_strategy` + `validate_text_localization_plan` 已保证高置信 TextTrack 走翻译
策略（REDRAW/REPLACE_OVERLAY/信息卡），BRAND_MARK 硬红线 SKIP，UNKNOWN 兜底人工——未翻译
只发生在设计允许处。P4 Exit 未再单列画面文字端到端样本（VF-403 自带 34 测试 + opus
20/20 CONFIRMED 已覆盖）；真实"未翻译率"需真实 OCR 高置信轨样本，属 stop-condition。

### ④ 成片音画偏差 P95 ≤ 80ms —— 🔸 结构就绪，度量延后
句级配音无截断在 VF-404 `validate_tts_manifest`（word_timings 单调 + 不超总时长）结构性
保证；但"成片音画偏差 P95 ≤ 80ms"需**真实渲染 + 对成片重新提取音频/帧测量**（§11），
依赖 media-core RenderRuntime + golden media，属既有延后项（见 54c P3 Exit）。本关口只验
结构不变量，不验真实毫秒偏差。

## 结论

六条验收：**①②⑤⑥ 结构级全绿**（含非空跑护栏），③④ 诚实标注为"护栏已在 + 真实度量待
RenderRuntime/真实 OCR"。P4 本地化闭环的**判定逻辑、护栏、非阻塞与局部重跑作用域**均可
复现验证。跑 `tests/acceptance/` → 55 passed；相关 contracts/domain/provider-sdk 全套 →
1036 passed；lint 全绿；schema 零 drift。

**P4 CLOSED**（判定/护栏/作用域层面）。延后项（真实 ASR/OCR/VLM/TTS/LipSync 引擎 +
权重、AnalysisWorkflow 把 activity_cache_key 用起来、golden media 真实音画偏差度量）随
真实引擎接入补齐。下一阶段：**P5 审核与发布**（VF-501 Review Policy + Queue 起）。
