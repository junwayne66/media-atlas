"""效果反馈合同（docs/modules/44 §10 Performance Snapshot + 限流 + null 语义）。

VF-601 目标：**平台指标快照**——把发布后的帖子在 1/3/6/24/72h/7d 的表现按平台限流
抓成快照。

**红线（§10 null 语义）**：`只保存平台实际提供的指标，缺失保持 null`。因此每个指标字段都是
`… | None` 且**默认 None，绝不默认 0**——缺失 = 未知，永远不当作 0 参与后续统计/归因。
`extra="forbid"` + 全 Optional 让"连接器没上报的字段自然为 null"是结构保证，而非约定。

**stop-condition**：真实平台官方数据 API 回采（TikTok/抖音 Insights/Analytics 的 live
调用）需真实账号 + 应用审核 + 凭据。本层只做**快照合同 + 计划 + 能力上报**，不触真实平台：
`UnconfiguredMetricsConnector` 诚实 UNCONFIGURED；`FakeMetricsConnector` 回放注入快照，零网络。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.publish_preflight import AuthStatus, PublishPlatform


class MetricField(StrEnum):
    """§10 指标字段名——用于连接器上报"我这个数据源能提供哪些字段"。"""

    VIEWS = "VIEWS"
    WATCH_TIME = "WATCH_TIME"
    AVG_WATCH_TIME = "AVG_WATCH_TIME"
    COMPLETION_RATE = "COMPLETION_RATE"
    LIKES = "LIKES"
    COMMENTS = "COMMENTS"
    SHARES = "SHARES"
    SAVES = "SAVES"
    FOLLOWS = "FOLLOWS"
    IMPRESSIONS = "IMPRESSIONS"
    CLICK_THROUGH_RATE = "CLICK_THROUGH_RATE"


class PerformanceSnapshot(ContractModel):
    """§10 表现快照。**每个指标字段缺失保持 null，绝不填 0**（红线）。

    非指标元数据（platform/post_id/account/observed_at/age/source_confidence）是必填事实；
    只有平台"实际提供的表现指标"才 Optional——它们的 null 表示"平台没给这个数"，
    下游统计/归因必须把 null 当作"未知"跳过，永远不能当 0。
    """

    id: str = Field(min_length=1)
    platform: PublishPlatform
    platform_post_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    observed_at: datetime
    age_hours: float = Field(ge=0, description="发布至观测时的小时数（可为小数）")

    # --- 平台实际提供的指标：全 Optional，缺失保持 null（§10 红线）---------------
    views: int | None = Field(default=None, ge=0)
    watch_time_ms: int | None = Field(default=None, ge=0, description="总观看时长")
    avg_watch_time_ms: int | None = Field(default=None, ge=0, description="平均观看时长")
    completion_rate: float | None = Field(default=None, ge=0, le=1)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    follows: int | None = Field(default=None, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    click_through_rate: float | None = Field(default=None, ge=0, le=1)

    # 数据来源可信度（1.0 官方 API / 较低为抓取等）——非指标，必填、非空。
    source_confidence: float = Field(ge=0, le=1)


class SnapshotSchedule(ContractModel):
    """一个帖子的快照计划（§10 建议 1/3/6/24/72h/7d，按平台限流调整）。

    `planned_ages_hours` 是计划观测的年龄点（小时）；`captured_ages_hours` 是已抓取的年龄点。
    domain 据 published_at + now 算"现在该抓哪个/下一个定时器何时触发"。
    """

    id: str = Field(min_length=1)
    platform: PublishPlatform
    platform_post_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    published_at: datetime
    planned_ages_hours: list[float] = Field(min_length=1)
    captured_ages_hours: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ages(self) -> "SnapshotSchedule":
        if any(a < 0 for a in self.planned_ages_hours):
            raise ValueError("planned_ages_hours 不能为负")
        if len(set(self.planned_ages_hours)) != len(self.planned_ages_hours):
            raise ValueError("planned_ages_hours 不能重复")
        planned = set(self.planned_ages_hours)
        if not set(self.captured_ages_hours) <= planned:
            raise ValueError("captured_ages_hours 必须是 planned_ages_hours 的子集")
        return self


class MetricsConnectorCapability(ContractModel):
    """指标连接器上报的能力 + 授权 + 限流（§3 "Connector 返回能力，不由 UI 猜" 的效果反馈版）。

    `provided_fields` 声明该数据源能提供哪些指标——让快照里的 null 是"源本就不提供"的有据缺失，
    而非漏抓。`min_seconds_between_calls` 是平台限流下的最小调用间隔，domain 据此排程。
    """

    platform: PublishPlatform
    available: bool = Field(description="该数据源当前是否可用")
    auth_status: AuthStatus
    provided_fields: list[MetricField] = Field(default_factory=list)
    min_seconds_between_calls: int = Field(default=0, ge=0, description="限流：最小调用间隔（秒）")
    notes: str | None = None
