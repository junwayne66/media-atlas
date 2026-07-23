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
