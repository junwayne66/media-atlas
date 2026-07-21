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
