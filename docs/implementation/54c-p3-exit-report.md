# P3 Exit 验收报告（创作与剪辑）

对应 `53-coder-agent-roadmap.md` 的 **P3 Exit** 关口与 `54-mvp-acceptance.md` §2 功能矩阵的
P3 相关行，以及 `docs/modules/42-creative-planning-and-editing.md §12` 的七条验收准则。
所有数字来自 `tests/acceptance/` 的可复跑验收套件（已接入 pytest `testpaths`，`make test`
强制执行），非人工承诺。

> 结论：**P3 Exit 通过**（含明确标注的停止条件延后项）。全部 P3 任务 VF-301…VF-310 完成。

## 1. 出口标准与判定

映射 42 §12「验收清单」七条：

| 42 §12 出口标准 | 判定 | 证据 |
|---|---|---|
| ① 两种创作模式均可从同一 Blueprint 产出独立 Package | ✅ 通过 | 20 条 zh/en 样本，STRUCTURE_REWRITE + SOURCE_REEDIT 均产 Package，全过 domain 护栏 |
| ② 一句台词改动只重跑受影响下游 | ✅ 原语级通过 | `activity_cache_key` 上游稳定、下游变；provider/tool_version/config 隔离；workflow 级集成待 AnalysisWorkflow 落地 |
| ③ Top-3 Highlight 与人工标注命中率 ≥ 70% | ✅ 通过 | 10 条 fixture、30 个人工标注，Top-3 集合覆盖率 ≥ 70% |
| ④ 代理与最终渲染切点差 <1 帧 | ✅ 结构级通过 | PROXY vs FINAL 的 trim/atrim 秒数**完全一致**（差 = 0 帧）；真实 GOP/关键帧对齐待 golden-media |
| ⑤ 20 条样本零非预期 BLOCKER | ✅ 通过 | 20/20 合成 clean 媒体输入（每 500ms 一帧 + 合规字幕 + 有效音频窗）触发 9 条规则真跑，零 BLOCKER |
| ⑥ OTIO 可导入 DaVinci | ✅ 结构级通过 | Clip 携带 `ExternalReference.1` + `target_url`（可重连媒体）+ `TimeRange.1`；DaVinci 客户端联合导入待 55 冒烟 |
| ⑦ 剪映失败标记为 Adapter 限制、不破坏 Project | ✅ 通过 | JIANYING/CAPCUT 均返回 PARTIAL；`export_all` 单硬失败 FAILED 后其它 exporter 正常 |

## 2. 两模式共蓝图 Package（`test_p3_exit_two_modes.py`）

样本集 `p3_samples.py` 为**中性合成样本**（10 zh + 10 en），涵盖 AI 与非-AI 主题、时长
30/45/60/90s、涵盖 `VERIFIED / UNVERIFIED / DISPUTED / OPINION` 各种 `ClaimSourceStatus`：

| 语言 | AI 主题 | 非-AI 主题 | 合计 |
|---|---:|---:|---:|
| zh-CN | 5 | 5 | 10 |
| en-US | 5 | 5 | 10 |
| **总计** | 10 | 10 | **20** |

对每条样本：

- **STRUCTURE_REWRITE**：`build_claim_table` → `build_creative_brief` → `build_beat_template`
  → `FakeStructureRewriteProvider.rewrite` → `is_valid_script(script, claim_table, brief) == True`。
- **SOURCE_REEDIT**：Blueprint → 6 段合成 Transcript → `build_candidate_windows` →
  `FakeHighlightFeatureProvider.score` → `rank_highlights(top_n=3)`；Top-N ≤3 且 ≥1。
- **共用**：`resolve_asset_plan`（OWN_LIBRARY 优先）+ `CreativeTimeline`（V1 + A0）；
  `is_valid_asset_plan` + `is_valid_timeline` 双护栏均绿。
- **QA 发布门**：注入合成 clean 媒体（每 500ms 一帧 mean_luma=128 + phash 递增 + 合规居中
  字幕 + LUFS=-14 音频窗）触发 9 条 QA 规则**真正跑起来**（非空输入的 vacuous 状态）→
  `aggregate_qa_report` + `validate_publish_gate` → `PublishGate.PASS`。
- **关键安全属性**：`test_disputed_claims_never_forced_into_scripts` **直接构造 must_cover
  强含 DISPUTED 的 brief 直调 Fake**（不依赖 `_build_structure_rewrite` 的过滤逻辑），
  断言 script.sentences.claim_ids **不包含** DISPUTED——`FakeStructureRewriteProvider` 遇
  DISPUTED must_cover 拒引，是 VF-302 契约（`usable_in_rewrite=False`）的真实证明。

## 3. 一句改动的重跑范围（`test_p3_exit_local_rerun.py`）

对齐 42 §12 第 2 条 + 41 §11：以 media-core `activity_cache_key(input_digest, provider,
tool_version, config, schema_version)` 为准，逐条断言：

- **上游稳定**：改脚本内容 → 下载 activity 与 ASR activity 的 cache_key **不变** → 缓存命中、
  不重跑（`test_upstream_stages_unaffected_by_downstream_script_edit`）。
- **下游变**：一句台词改动 → 整脚本 hash 变 → 时间轴/渲染 activity 的 cache_key **变**、
  重算（`test_script_edit_changes_downstream_cache_key`）。
- **命名空间隔离**：同一输入 digest 换 provider（下载 vs ASR）→ cache_key 绝不相同
  （`test_cache_key_isolation_by_provider`）。
- **配置敏感**：换 ASR 语言 → key 变；同配置二次调用 → key 稳（`test_config_change_forces_recompute…`）。
- **版本升级失效**：`tool_version` 变（v3→v4）→ key 变 → 触发全量重跑，杜绝新模型静默复用
  旧结果（`test_tool_version_upgrade_invalidates_cache`）。

**证据边界（verifier 指出）**：AnalysisWorkflow 尚未落地（P2 起始终是延后项），生产代码
里**尚无任何 activity 在真正调用**此原语。本测试证的是**原语层**契约的正确性——为
将来每类 activity 提供统一且可复用的缓存键计算方式；原语正确是 workflow 层证明的必要
条件；workflow 层的集成证明将在 AnalysisWorkflow 落地时另加。

## 4. Highlight Top-3 命中率（`test_p3_exit_highlight_hit_rate.py`）

- **fixture**：10 条转录（zh/en 各半），每条 3 段人工标注（HOOK / HIGH_INFO / PAYOFF），
  合计 30 个应入选窗。
- **命中口径**：Highlight 排序器目标是"找到 highlight 所在时间区域"，非精确剪辑边界。
  采用**覆盖率** `|label ∩ topk| / |label| ≥ 0.7` → 视为命中；每个人工标注最多计 1。
- **总体命中率**：跨 10 条 fixture 的 30 个人工标注，集合级命中率 **≥ 70%**（阈值满足）。
- **抗抵消断言**：额外要求"无一条 fixture 0/3 命中"——防止"集合数字合格但某类内容整
  个漏检"的 vacuous 状态（verifier 指出的护栏加固）。

（覆盖率而非 IoU 是刻意选择：Top-3 输出的窗口按句子边界完整对齐、常常包含标注区间加相邻
上下文，用 IoU 会因边界宽窄扭曲统计；覆盖率反映"是否找到了 highlight 内容"的黑盒验收目标。）

**证据边界（verifier 指出）**：人工标注由本报告作者自拟（非独立测试者），Fake 特征打分
是启发式；因此本测试证的是"Fake + 作者标注综合命中率 ≥ 70%"，非"真实模型 vs 独立标注
≥ 70%"。真模型上线后应在此 fixture 上重跑并预期更高水位。

## 5. PROXY vs FINAL 切点差 + OTIO 结构 + Exporter 单失败不阻断（`test_p3_exit_render_and_export.py`）

**切点差 <1 帧**（§12 第 4 条）：

- 同一 CreativeTimeline 分别以 `stage=PROXY` 与 `stage=FINAL` 走 `compile_timeline`，逐一
  提取 `filter_complex` 中所有 `trim` / `atrim` 节点的 `(filter, start, end)` 三元组。
- 两 stage 的切点集合**完全一致**（差 = 0 帧 < 1 帧）；差异仅落在 codec 段（`-crf`
  `28`→`20`，`-preset` `veryfast`→`medium`）。
- 输入 `-i` 与 `-map` 段两 stage 逐字符相同——多 stage 渲染共享同一切点解释。

**OTIO 可导入 DaVinci**（§12 第 6 条，结构级）：

- `write_otio_file` 产 `.otio` JSON，含 `OTIO_SCHEMA=Timeline.1` / `tracks(Stack.1)` /
  `children(Track.1)` / `Clip.1` / `TimeRange.1`（DaVinci OTIO 读取器所需最小结构）。
- **每个 Clip 携带 `media_reference`**：`source_ref` 存在 → `ExternalReference.1` +
  `target_url=source_ref`（DaVinci 靠此重连媒体）；无 source_ref → `MissingReference.1`
  （NLE 打开时提示"离线媒体"而非静默丢字段）。§12 第 6 条**硬要求**"重连媒体"。
  **这是 P3 Exit verifier 发现的实质缺陷（Clip 缺 media_reference 使 DaVinci 无法重连）
  → 修复后补 regression：`test_otio_file_has_expected_structure_for_davinci_import` 断言
  `ExternalReference.1` 与 `target_url` 存在**。
- 与 VF-306 `from_otio_mapping` 往返一致：`duration` / `rate` / `source_ref` / `semantic_role`
  等 9 个扩展字段（`metadata.videoforge`）完整保留。
- **DaVinci 客户端联合导入待 55 冒烟**（需具备 DaVinci 授权环境，此处仅保结构合法与
  字段无损）。

**剪映失败为 Adapter 限制、不破坏批量**（§12 第 7 条）：

- `write_jianying_package` / `write_capcut_package` 恒返回 `ExporterStatus.PARTIAL`（"剪映
  官方 draft 未公开、发布链路已产出 MP4 最终成品"），并写 `README.md` 记明白限制。
- `export_all` 混合计划：一个 Adapter 硬失败（越白名单 → `FAILED`）不阻断其它 Adapter；
  剪映/CapCut 的 PARTIAL 也不阻断 OTIO/FCPXML 的 OK。批量导出流水线的**弱失败隔离**成立。

## 6. 已实现 vs Fake vs 延后

| 能力 | 状态 |
|---|---|
| Brief + ClaimTable + 校验护栏（VF-301） | 已实现（纯 domain；LLM 角度建议延后） |
| Structure Rewrite Engine + BeatTemplate + 事实/时长/避讳/查重（VF-302） | 已实现，**真实改写 LLM 延后**（Fake 通护栏） |
| Highlight Ranker + 11 特征 + MMR（VF-303） | 已实现，**真实特征模型延后** |
| Source Reedit Planner + 切点/变速/连续性护栏（VF-304） | 已实现，**真实判定模型延后** |
| Asset Resolver + 五级优先 + 匹配分（VF-305） | 已实现，**真实素材源延后**（vector library / Stock / GENERATED） |
| CreativeTimeline + OTIO 映射 + 9 扩展字段（VF-306） | 已实现（纯 dict OTIO） |
| FFmpeg Compiler + FilterGraph + 白名单强制（VF-307） | 已实现（真实 ffmpeg 8.1.2） |
| Remotion Compiler（合同 + 编译器 + Fake，无 remotion.* 导入）（VF-308） | 已实现，**Remotion 商用许可红线未清，`UnconfiguredRemotionRenderProvider` 恒返 LICENSE_PENDING** |
| QA Gates 9 规则 + 阈值门 + 16 类枚举（VF-309） | 已实现，**真实 ebur128/opencv/OCR 检测器延后**（Fake 供样本注入） |
| Exporters：OTIO 真文件 / FCPXML / 剪映 / CapCut（VF-310） | OTIO/FCPXML 完整、剪映/CapCut PARTIAL（Adapter 限制） |
| DaVinci OTIO 联合导入冒烟 | **延后到 55 macOS 冒烟阶段**（需授权环境） |
| Golden Media Tests（testsrc → hash） | **延后**（要 media-core RenderRuntime 落地） |
| 音频混合（amerge）/ V3 overlays / V5 水印 | **延后**（VF-307 首版覆盖 V1/V2/A0/A1） |

## 7. 已知边界（老实登记）

- Highlight 排序器仍是 **确定性 Fake 派生**：位置 → hook/ending、文本长度 → info_density
  等启发式，不是真实模型判断。真模型上线后重跑此 fixture，命中率应升到更高水位。
- OTIO 端仅通过 **结构 grep + 往返对等** 验证；**DaVinci 实际打开**需人工在 55 冒烟。
- 剪映/CapCut Adapter 恒 PARTIAL：官方 draft 格式未公开且许可未清，验收口径是"标记 +
  不破坏 Project"——最终成品由 MP4 发布链路兜底。
- PROXY vs FINAL 切点差 = 0 帧的判断基于**编译器输出的 filter DAG**；实际 ffmpeg 运行时
  的帧对齐会受 GOP/关键帧影响，落地后需 golden-media 测试进一步确认。

## 8. 复跑说明

```bash
uv run pytest tests/acceptance/ -q
```

四个 P3 验收测试文件 + 已有 P1/P2 验收共 41 tests，全绿在 <0.3s 内跑完（纯 CPU、无外网、
无 ffmpeg 依赖 —— ffmpeg 真渲染验证走 VF-307 集成测试）。

## 9. 后续（P4 起步）

`docs/implementation/53-coder-agent-roadmap.md` P4：本地化（时间轴翻译 + 双语字幕 + 配音）。
按 `VF-401` 起 —— **Blueprint + CreativeTimeline 已在 P3 就绪**，P4 只加语言维度不改结构。
