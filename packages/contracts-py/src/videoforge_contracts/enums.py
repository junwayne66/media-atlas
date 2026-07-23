from enum import StrEnum


class CreationMode(StrEnum):
    """两种二创模式（docs/architecture/31 §5）。"""

    STRUCTURE_REWRITE = "STRUCTURE_REWRITE"
    SOURCE_REEDIT = "SOURCE_REEDIT"


class ProjectStatus(StrEnum):
    """Project 状态机（docs/architecture/31 §3）。FAILED 不是删除。"""

    DRAFT = "DRAFT"
    INGESTING = "INGESTING"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    EDITING = "EDITING"
    LOCALIZING = "LOCALIZING"
    QC = "QC"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    PUBLISHING = "PUBLISHING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    PUBLISHED = "PUBLISHED"
    MEASURING = "MEASURING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExecutionPolicy(StrEnum):
    """任务路由策略（docs/architecture/30 §6）。"""

    LOCAL_ONLY = "LOCAL_ONLY"
    LOCAL_PREFERRED = "LOCAL_PREFERRED"
    CLOUD_PREFERRED = "CLOUD_PREFERRED"
    CLOUD_ONLY = "CLOUD_ONLY"


class ProviderType(StrEnum):
    """Provider 类型全集（docs/10-module-overview.md §4）。"""

    SOURCE_CONNECTOR = "SourceConnector"
    DOWNLOAD_PROVIDER = "DownloadProvider"
    ASR_PROVIDER = "ASRProvider"
    OCR_PROVIDER = "OCRProvider"
    LLM_PROVIDER = "LLMProvider"
    VLM_PROVIDER = "VLMProvider"
    TTS_PROVIDER = "TTSProvider"
    LIPSYNC_PROVIDER = "LipSyncProvider"
    STOCK_MEDIA_PROVIDER = "StockMediaProvider"
    GENERATIVE_MEDIA_PROVIDER = "GenerativeMediaProvider"
    RENDER_PROVIDER = "RenderProvider"
    TIMELINE_EXPORTER = "TimelineExporter"
    PUBLISH_CONNECTOR = "PublishConnector"
    METRICS_CONNECTOR = "MetricsConnector"


class IsolationLevel(StrEnum):
    """许可证/接口隔离等级（docs/20-open-source-landscape.md §3）。"""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class StorageBackend(StrEnum):
    S3 = "s3"
    LOCAL_CACHE = "local_cache"


class TrendStage(StrEnum):
    """趋势阶段状态机（docs/modules/40-trend-intelligence.md §6）。"""

    EMERGING = "EMERGING"
    RISING = "RISING"
    PEAK = "PEAK"
    SATURATED = "SATURATED"
    DECAYING = "DECAYING"
    ARCHIVED = "ARCHIVED"


class TextTrackKind(StrEnum):
    """文本轨类型（docs/modules/41 §8）。区分字幕/标题/UI/品牌水印/场景文字。"""

    CAPTION = "CAPTION"  # 字幕（底部）
    TITLE = "TITLE"  # 标题（顶部/大字）
    LOWER_THIRD = "LOWER_THIRD"  # 下三分区信息条
    UI = "UI"  # 界面元素（角落/小）
    SCENE_TEXT = "SCENE_TEXT"  # 场景内文字
    BRAND_MARK = "BRAND_MARK"  # 品牌标/水印（小、角落、持久）
    UNKNOWN = "UNKNOWN"


class FrameSampleReason(StrEnum):
    """代表帧被选中的原因（docs/modules/41 §9）。VLM 只分析代表帧，禁逐帧。"""

    KEYFRAME = "KEYFRAME"  # 起始/关键帧，保底覆盖
    SCENE_CUT = "SCENE_CUT"  # 场景切换（内容变化）
    TEXT_CHANGE = "TEXT_CHANGE"  # 新文本轨出现
    SPEAKER_CHANGE = "SPEAKER_CHANGE"  # 说话人切换
    LOW_CONFIDENCE = "LOW_CONFIDENCE"  # 上游 OCR/ASR 低置信，需 VLM 消歧
    PERIODIC = "PERIODIC"  # 长静止段的周期性采样，保证覆盖


class RhetoricalBeatKind(StrEnum):
    """表达层节拍（docs/modules/41 §10.1）。UNCLASSIFIED 允许存在以保覆盖率。"""

    HOOK = "HOOK"  # 钩子
    QUESTION = "QUESTION"  # 提问
    EVIDENCE = "EVIDENCE"  # 证据
    CONTRAST = "CONTRAST"  # 对比
    DEMO = "DEMO"  # 演示
    CONCLUSION = "CONCLUSION"  # 结论
    CTA = "CTA"  # 行动号召
    UNCLASSIFIED = "UNCLASSIFIED"


class VisualBeatKind(StrEnum):
    """视觉层节拍（docs/modules/41 §10.1）。"""

    PERSON = "PERSON"  # 人物出镜
    SCREEN_RECORD = "SCREEN_RECORD"  # 屏幕录制
    PRODUCT = "PRODUCT"  # 产品
    B_ROLL = "B_ROLL"  # 空镜/补充画面
    CARD = "CARD"  # 图卡/字卡
    UNKNOWN = "UNKNOWN"


class ClaimSourceStatus(StrEnum):
    """Claim 的来源核验状态（docs/modules/41 §10.1）。"""

    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    DISPUTED = "DISPUTED"
    OPINION = "OPINION"


class HighlightReason(StrEnum):
    """热门片段候选的理由码（docs/modules/42 §5.3）。正向亮点 + 谨慎项。"""

    HOOK_QUOTE = "HOOK_QUOTE"  # 开场钩子强
    CLEAR_PAYOFF = "CLEAR_PAYOFF"  # 结尾有回报/结论清晰
    HIGH_INFO_DENSITY = "HIGH_INFO_DENSITY"  # 信息密度高
    SURPRISE = "SURPRISE"  # 意外/冲突
    EMOTIONAL_PEAK = "EMOTIONAL_PEAK"  # 情绪能量高
    SELF_CONTAINED = "SELF_CONTAINED"  # 自足，脱离上下文可懂
    STRONG_TOPIC = "STRONG_TOPIC"  # 主题相关性强
    VISUAL_ACTION = "VISUAL_ACTION"  # 画面有动作/变化
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"  # 谨慎：强依赖上下文
    TECHNICAL_DEFECT = "TECHNICAL_DEFECT"  # 谨慎：存在技术瑕疵


class HighlightLabel(StrEnum):
    """人工对候选的处置（docs/modules/42 §5.3）。选中/放弃原因成为训练标签。"""

    UNREVIEWED = "UNREVIEWED"  # 未审
    SELECTED = "SELECTED"  # 人工选中
    REJECTED = "REJECTED"  # 人工放弃


class EditOpKind(StrEnum):
    """原片重剪操作（docs/modules/42 §4.1）。"""

    KEEP = "KEEP"  # 保留源片段到输出
    DELETE = "DELETE"  # 删除（静音/口头禅/重复/低信息）
    MUTE = "MUTE"  # 静音但保画面
    SPEED = "SPEED"  # 变速（仅允许区间）
    REFRAME = "REFRAME"  # 重构图建议（16:9→9:16 跟随）


class ReframeFollow(StrEnum):
    """重构图跟随目标（docs/modules/42 §4.1）。"""

    SPEAKER = "SPEAKER"
    PRODUCT = "PRODUCT"
    UI = "UI"
    FACE = "FACE"
    CENTER = "CENTER"


class ContinuityRuleKind(StrEnum):
    """连续性处理（docs/modules/42 §4.2）。"""

    J_CUT = "J_CUT"  # 声音先入
    L_CUT = "L_CUT"  # 声音后出
    INSERT_BROLL = "INSERT_BROLL"  # 朝向/视线冲突插空镜/图卡
    JUMPCUT_SMOOTH = "JUMPCUT_SMOOTH"  # jump cut 用推拉/构图变化平滑
    BEAT_ALIGN = "BEAT_ALIGN"  # 音乐按 Beat Grid 对齐（不破句）


class AssetRole(StrEnum):
    """素材在时间线上的角色（docs/modules/42 §6.1）。"""

    TALKING_HEAD = "TALKING_HEAD"
    SCREEN_DEMO = "SCREEN_DEMO"
    B_ROLL = "B_ROLL"
    INFO_CARD = "INFO_CARD"
    LOGO = "LOGO"
    CHART = "CHART"
    LOWER_THIRD = "LOWER_THIRD"
    PLACEHOLDER = "PLACEHOLDER"


class AssetSource(StrEnum):
    """素材来源层级（docs/modules/42 §6.2 Resolver 顺序）。"""

    SOURCE = "SOURCE"  # 授权原片
    OWN_LIBRARY = "OWN_LIBRARY"  # 自有素材库
    STOCK = "STOCK"  # 商业/许可素材
    GENERATED = "GENERATED"  # AI 生成
    PLACEHOLDER = "PLACEHOLDER"  # 数字人/信息卡/屏幕录制占位


class AssetLicenseType(StrEnum):
    """素材许可类型（每个 ResolvedAsset 必带来源与许可以便追溯）。"""

    OWNED = "OWNED"  # 自有版权/授权原片
    LICENSED_STOCK = "LICENSED_STOCK"  # 采购的商业许可
    ROYALTY_FREE = "ROYALTY_FREE"  # 免版税
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    GENERATED_MODEL = "GENERATED_MODEL"  # 生成式模型输出
    PLACEHOLDER = "PLACEHOLDER"  # 占位（未来替换）


class RenderStage(StrEnum):
    """渲染阶段（docs/modules/42 §8.3）。PROXY 供预览/审校，FINAL 供发布。"""

    PROXY = "PROXY"
    FINAL = "FINAL"


class RenderTargetKind(StrEnum):
    """渲染目标（编解码 + 封装）。"""

    MP4_H264 = "MP4_H264"
    MP4_H265 = "MP4_H265"
    MOV_PRORES = "MOV_PRORES"
    WEBM_VP9 = "WEBM_VP9"


class QASeverity(StrEnum):
    """QA 严重级（docs/modules/42 §11）。BLOCKER 一处即拒；MAJOR 超阈升级；MINOR/INFO 记录。"""

    BLOCKER = "BLOCKER"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


class QAFindingKind(StrEnum):
    """QA 检测项（docs/modules/42 §11）。覆盖视频/音频/字幕/合规四大类。"""

    # 视频质量
    BLACK_FRAME = "BLACK_FRAME"  # 黑帧
    FROZEN_FRAME = "FROZEN_FRAME"  # 冻帧
    FLICKER = "FLICKER"  # 频闪
    DUPLICATE_FRAMES = "DUPLICATE_FRAMES"  # 重复帧
    HOLE = "HOLE"  # 时间轴异常空洞
    # 音频质量
    VOICE_TAIL_CUT = "VOICE_TAIL_CUT"  # 人声尾部截断
    ABRUPT_SILENCE = "ABRUPT_SILENCE"  # 突兀静音
    LOUDNESS_OUT_OF_RANGE = "LOUDNESS_OUT_OF_RANGE"  # 响度越界（LUFS）
    TRUE_PEAK_CLIP = "TRUE_PEAK_CLIP"  # True Peak 爆表
    # 字幕
    CAPTION_OFF_SAFE_AREA = "CAPTION_OFF_SAFE_AREA"  # 字幕出安全区
    CAPTION_OVERLAP = "CAPTION_OVERLAP"  # 字幕重叠
    # 构图 / 视觉
    BROLL_RATIO_LOW = "BROLL_RATIO_LOW"  # B-roll 占比不足
    SUBJECT_CUT = "SUBJECT_CUT"  # 主体被裁
    UI_CROP = "UI_CROP"  # 关键 UI 被裁
    CLEANUP_FLICKER = "CLEANUP_FLICKER"  # 清理区时序闪烁
    # 时长一致性
    DURATION_MISMATCH = "DURATION_MISMATCH"  # Timeline 与输出总时长/帧数不一致


class RemotionComposition(StrEnum):
    """Remotion 组件类型（docs/modules/42 §8.3）。每个映射到 packages 中一个 React 组件路径。"""

    CAPTIONS = "CAPTIONS"  # 动态字幕（V4）
    INFO_CARD = "INFO_CARD"  # 信息卡片（V3）
    DATA_CHART = "DATA_CHART"  # 数据图形（V3）
    BRAND_ANIMATION = "BRAND_ANIMATION"  # 品牌动效（V5）
    LOWER_THIRD = "LOWER_THIRD"  # 第三部字幕/标题条


class TrackKind(StrEnum):
    """时间线轨道类型（docs/modules/42 §8.1）。V0..V5 视频层 / A0..A3 音频层 / M0 语义标记。"""

    V0_BACKGROUND = "V0_BACKGROUND"
    V1_PRIMARY_VIDEO = "V1_PRIMARY_VIDEO"
    V2_BROLL_SCREEN = "V2_BROLL_SCREEN"  # B-roll / Screen Demo
    V3_INFO_CARDS = "V3_INFO_CARDS"  # Info Cards / Generated Visuals
    V4_CAPTIONS = "V4_CAPTIONS"  # 字幕 / 屏幕文字
    V5_OVERLAYS = "V5_OVERLAYS"  # Brand overlay
    A0_ORIGINAL = "A0_ORIGINAL"  # 原声对白
    A1_DUB = "A1_DUB"  # 配音
    A2_MUSIC = "A2_MUSIC"
    A3_SFX = "A3_SFX"  # SFX / Ambience
    M0_MARKERS = "M0_MARKERS"  # 语义标记 / Claims / Review Notes
