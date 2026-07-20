# M04–M07：二创规划、热门剪辑、素材与渲染

## 1. 输入与输出

输入：`CreativeOpportunity`、`VideoBlueprint`、频道画像、模板版本、语言/平台目标、素材策略。  
输出：`CreativeBrief`、`ScriptVersion`、`HighlightCandidate[]`、`AssetPlan`、`CreativeTimeline`、代理/最终 Render。

## 2. CreativeBrief

```yaml
objective: "45 秒解释某 AI 产品更新对普通用户的真实影响"
audience: "中文 AI 工具用户"
platform: "douyin"
duration_target_ms: 45000
creation_mode: "STRUCTURE_REWRITE"
hook:
  type: "counter_intuitive_claim"
  promise: "告诉观众一个参数表没说的限制"
angle: "实测成本与局限"
must_cover_claim_ids: [claim_1, claim_4]
avoid: ["照抄原标题", "未经证实的性能结论"]
visual_mix:
  talking_head: 0.25
  screen_demo: 0.35
  broll: 0.20
  info_card: 0.20
cta: "评论区说你最想测试的场景"
```

Brief 必须引用热点证据/Claims；模型生成的新增事实进入 `UNVERIFIED`，发布前不能自动通过。

## 3. 结构重写模式

### 3.1 Blueprint → Beat Template

将参考视频抽象为：

```text
0–3s  Hook: 反常识结论
3–10s Context: 更新是什么
10–25s Proof: 实测/示例
25–36s Constraint: 限制或反例
36–43s Takeaway: 适合谁
43–45s CTA
```

只复用节拍功能和时长比例，不复用原句、原配音、特有画面或品牌表达。

### 3.2 新脚本生成

1. 选定角度和受众。
2. 建立 `ClaimTable`：事实、证据、时效、置信度、允许表述。
3. 生成 Beat Sheet。
4. 生成中性语义脚本（Canonical Script）。
5. 按平台/语言做文风 Adaptation。
6. 检查重复度、事实、时长预算和禁用词。
7. 产出可逐句编辑的 `ScriptVersion`。

时长估算使用语言语速区间而非字符粗算；每句有 `target_duration_ms`。

## 4. 原片重剪模式

### 4.1 候选操作

- 删除静音、口头禅、重复或低信息段。
- 按新叙事重排片段。
- 选定 Highlight 窗口并扩展上下文。
- 16:9→9:16 智能重构图；跟随说话人/产品/UI。
- 新增旁白、动态字幕、标题卡、B-roll、SFX 和音乐。
- 变速只在允许区间，语音段优先保持自然节奏。
- 画面轻度调色、去抖、裁切、遮挡和布局重构。

### 4.2 保持连续性

- 对话/J-cut/L-cut 保持语义和呼吸。
- 人物朝向、视线和运动方向冲突时插 B-roll/图卡。
- Jump cut 间隔过短时用推拉/构图变化或切镜处理。
- 音乐按 Beat Grid 对齐，但不能为了卡点破坏一句完整表达。

## 5. 热门片段识别

### 5.1 候选窗口生成

- 以句子/语义 Beat 边界生成 12–75 秒窗口。
- 允许窗口扩展到问题前文/结论后文。
- 强制避免句中截断、呼吸声突断和镜头过渡中断。
- 对短视频重剪可生成 5–30 秒高光；对长访谈生成 20–90 秒片段。

### 5.2 评分

```text
highlight_score =
    0.20 * hook_strength
  + 0.16 * self_containedness
  + 0.14 * information_density
  + 0.12 * surprise_or_conflict
  + 0.10 * emotional_energy
  + 0.09 * topic_relevance
  + 0.07 * visual_activity
  + 0.06 * speaker_prominence
  + 0.06 * ending_payoff
  - 0.12 * context_dependency
  - 0.08 * technical_defect
```

`predicted_retention` 后续作为校准项加入，不在无训练数据时伪装成准确预测。

### 5.3 去重与多样性

- 对重叠 >70% 的窗口只保留高分者。
- 用 MMR 平衡分数与主题/人物/视觉多样性。
- 返回 Top-N 以及 `HOOK_QUOTE`、`CLEAR_PAYOFF`、`HIGH_INFO_DENSITY` 等理由。
- 人工选中/放弃原因成为训练标签。

## 6. 素材规划和解析

### 6.1 `AssetPlanSlot`

```json
{
  "slot_id": "slot_12",
  "time_range_ms": [8200, 12400],
  "role": "SCREEN_DEMO",
  "query": "AI app macOS local inference settings",
  "semantic_requirements": ["must show settings panel"],
  "composition": {"safe_area": "center", "aspect_ratio": "9:16"},
  "allowed_sources": ["SOURCE", "OWN_LIBRARY", "STOCK", "GENERATED"],
  "fallback": "INFO_CARD"
}
```

### 6.2 Resolver 顺序

1. 评分合格的授权原片。
2. 自有素材库（语义向量 + 标签 + 使用历史）。
3. 商业/许可素材 Provider。
4. AI 图片/视频 Provider。
5. 数字人/信息卡/屏幕录制占位。

匹配分：语义、构图、分辨率、运动、颜色、人物/品牌限制、重复使用惩罚。每个素材带来源、许可证/授权、检索词和使用区间。

## 7. 可见文字/遮挡物清理（授权素材）

### 7.1 检测

- 静态：跨帧低位移、位置稳定、与场景无关；计算时间方差和边缘稳定性。
- 动态：OCR/Logo 检测 + 光流/特征跟踪 + 分割 Mask。
- 区分平台 UI、字幕、品牌标志、场景内文字和待翻译标题。

### 7.2 处理策略

按损伤最小原则选择：

1. 重构图/裁切或用设计层覆盖。
2. 使用相邻/前后帧内容重建。
3. 时空 Inpainting，Mask 羽化和运动一致性。
4. 大面积或主体遮挡时，替换为 B-roll/信息卡，不强行修复。

保留原始 SourceAsset 和处理 Mask；输出 `cleanup_confidence`、`affected_area_ratio`、`temporal_consistency_score`。明显闪烁或鬼影时 QC 失败。

## 8. CreativeTimeline

### 8.1 轨道

```text
V0 Background
V1 Primary Video
V2 B-roll / Screen Demo
V3 Info Cards / Generated Visuals
V4 Captions / On-screen Text
V5 Overlays / Brand
A0 Original Dialogue
A1 Dubbed Voice
A2 Music
A3 SFX / Ambience
M0 Semantic Markers / Claims / Review Notes
```

### 8.2 Segment 扩展

每个 Segment 除时间范围外包含：`source_ref`、`semantic_role`、`script_sentence_id`、`speaker_id`、`provenance_ref`、`template_slot`、`effects`、`crop_path`、`localization_policy`。

### 8.3 编译

- Timeline Validator 检查范围、重叠、媒体存在、帧率/采样率和必填槽位。
- FFmpeg Compiler 产生参数数组和 Filter Graph，不用 shell 拼接。
- Remotion Compiler 产生类型化 Props。
- 每次编译生成 `RenderManifest`，包括所有输入哈希和版本。

## 9. 模板系统

模板是版本化 JSON/YAML + 可选 Remotion 组件：

```text
format, safe areas, duration bounds
beat slots, track layout, typography
caption presets, transitions, color tokens
music policy, SFX policy, crop policy
language overrides, platform overrides
QC thresholds, review policy defaults
```

模板升级不改变历史 Project；新版本经过样本回归后才进入 `TRUSTED`。

## 10. NLE 导出

- OTIO：主交换格式，保存剪辑、标记、媒体引用和扩展元数据。
- DaVinci：优先 OTIO/FCPXML；导出后运行媒体路径和时码验证。
- 剪映：`pyJianYingDraft`/自研 Exporter；维护版本矩阵；新版草稿加密或 macOS 自动导出不可用时只输出包/说明。
- CapCut：独立 `pyCapCut`/草稿 Adapter，标记 experimental。

导出失败不影响 MP4 最终渲染。

## 11. QA

借鉴 `video-autopilot-kit`，实现：

- 黑帧、冻帧、频闪、重复帧、异常空洞。
- 人声尾部截断、突兀静音、响度/True Peak。
- 字幕与词级时间、字幕安全区和重叠。
- B-roll 占比、字幕/B-roll 语义匹配。
- 主体被裁、脸部出框、屏幕关键 UI 被裁。
- 清理区时序闪烁。
- Timeline 与输出总时长/帧数一致。

## 12. 验收

- 两种模式均可从同一 Blueprint 生成独立 Package。
- 修改一句脚本只重跑受影响 TTS/字幕/片段和最终 Render。
- Top-3 Highlight 人工命中目标 ≥ 70%（首期标注后评估）。
- 代理预览与最终渲染的切点差 < 1 帧。
- 20 条样本无非预期黑帧、空轨和音频尾部截断。
- DaVinci 导出在首期选定版本可导入并重连媒体。
- 剪映导出失败被标记为 Adapter 限制，不破坏系统 Project。

