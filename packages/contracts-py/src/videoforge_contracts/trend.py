from datetime import datetime

from pydantic import Field

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import TrendStage


class TrendItemSnapshot(ContractModel):
    """周期采集的原始平台观测（docs/modules/40 §3.1）。不可变——热度靠序列算。

    缺失指标保留 null，绝不填 0（40 §3.2）：区分"真的是 0"与"没采到"。
    """

    id: str = Field(min_length=1)
    observed_at: datetime
    platform: str = Field(min_length=1)
    region: str | None = None
    locale: str | None = None
    item_id: str = Field(min_length=1)
    author_id: str | None = None
    published_at: datetime | None = None
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    followers_at_observation: int | None = Field(default=None, ge=0)
    rank: int | None = Field(default=None, ge=1)
    hashtag_ids: list[str] = Field(default_factory=list)
    sound_id: str | None = None
    raw_artifact_id: str | None = Field(default=None, description="原始响应/页面证据 Artifact")
    collector_version: str = Field(min_length=1)
    source_confidence: float = Field(
        ge=0.0, le=1.0, description="官方/公开页/抓取/手工导入的可信度（40 §3.2）"
    )


class HotScoreWeights(ContractModel):
    """热度评分权重（docs/modules/40 §5）。权重是模板版本，不写死在代码，
    须经历史表现校准。默认值为文档基线。saturation/decay 为负向权重。"""

    # 权重是幅值（≥0）；saturation/decay 的负向由 scoring.hot_score 公式承载，
    # 不靠负权重表达。ge=0 挡掉坏模板，无上界以留校准空间。
    template_version: str = "v1"
    velocity: float = Field(default=0.24, ge=0.0)
    acceleration: float = Field(default=0.18, ge=0.0)
    engagement_efficiency: float = Field(default=0.14, ge=0.0)
    cross_platform_score: float = Field(default=0.13, ge=0.0)
    topic_fit: float = Field(default=0.12, ge=0.0)
    novelty: float = Field(default=0.10, ge=0.0)
    source_quality: float = Field(default=0.09, ge=0.0)
    saturation: float = Field(default=0.15, ge=0.0)
    decay: float = Field(default=0.12, ge=0.0)


class TrendSubScores(ContractModel):
    """归一化到 [0,1] 的子分数（40 §5）。velocity/acceleration/engagement/decay
    由快照序列算出；其余由聚类上下文/外部信号提供。"""

    velocity: float = Field(ge=0.0, le=1.0)
    acceleration: float = Field(ge=0.0, le=1.0)
    engagement_efficiency: float = Field(ge=0.0, le=1.0)
    cross_platform_score: float = Field(default=0.0, ge=0.0, le=1.0)
    topic_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    novelty: float = Field(default=0.0, ge=0.0, le=1.0)
    source_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    saturation: float = Field(default=0.0, ge=0.0, le=1.0)
    decay: float = Field(default=0.0, ge=0.0, le=1.0)


class TrendCluster(ContractModel):
    """跨平台/跨语言同事件信号聚类（docs/architecture/31 §1.1）。

    可版本化聚合：人工拆分/合并产生新版本，member_item_ids 与合并理由保留。
    """

    id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1, description="乐观并发；人工拆分/合并后不被无条件覆盖")
    title: str = Field(min_length=1)
    canonical_topic: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    member_item_ids: list[str] = Field(default_factory=list, description="成员 item 引用")
    snapshot_ids: list[str] = Field(default_factory=list)
    first_seen_at: datetime
    last_seen_at: datetime
    stage: TrendStage = TrendStage.EMERGING
    sub_scores: TrendSubScores | None = None
    hot_score: float | None = Field(default=None, ge=0.0, le=1.0)
    weights_version: str | None = Field(default=None, description="算 hot_score 用的权重模板版本")
    reason_codes: list[str] = Field(default_factory=list, description="可解释理由码（40 §10 ≥2）")
    embedding_ref: str | None = None
    source_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    vertical: str | None = Field(default=None, description="内容方向，如 ai-tech")
    created_at: datetime
    updated_at: datetime
