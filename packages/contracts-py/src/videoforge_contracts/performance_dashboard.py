"""效果反馈 Dashboard 合同（docs/modules/44 §11 归因：账号基线 + 分组 + 账号内相对指标）。

VF-602 目标：把已发布视频按 **模板/Hook/创建模式/时长/语言/发布时间** 分组，用**账号内相对指标**
（如 `views_at_24h / account_median_24h`）做**可解释统计和分桶**——**不训练黑盒"爆款模型"**（§11）。

**红线**：
- **账号内相对，绝不跨账号比较绝对播放**（§11）——一切分组统计都相对于**同一账号**的基线。
- **样本不足不排序**（§11 "有足够样本后再做排序"）——每组带 `enough_samples`，低于阈值只报不排。
- **null 语义（承接 VF-601）**：缺失指标(None)一律从基线/分组聚合中**排除，绝不当 0**。
- **可解释**：只有 中位数/分位数/计数——确定性、可复现，每个数都能追到它的样本集。

真实平台指标回采属 stop-condition；本层是纯读模型计算（domain），持久化 + Web UI 延后。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import CreationMode
from videoforge_contracts.performance import MetricField, PerformanceSnapshot
from videoforge_contracts.publish_preflight import PublishPlatform


class GroupDimension(StrEnum):
    """§11 分组维度。"""

    TEMPLATE = "TEMPLATE"
    HOOK = "HOOK"
    CREATION_MODE = "CREATION_MODE"
    DURATION_BUCKET = "DURATION_BUCKET"
    LANGUAGE = "LANGUAGE"
    PUBLISH_DAYPART = "PUBLISH_DAYPART"


class PerformanceFeatures(ContractModel):
    """一条已发布视频的归因特征（§11）。分组维度相关字段；缺失(None)的维度该视频不计入该分组。"""

    template_id: str | None = None
    hook_kind: str | None = None
    creation_mode: CreationMode | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    language: str | None = None
    publish_hour: int | None = Field(default=None, ge=0, le=23)
    publish_weekday: int | None = Field(default=None, ge=0, le=6)
    subtitle_style: str | None = None
    voice_ref: str | None = None
    has_music: bool | None = None
    qa_warning_count: int | None = Field(default=None, ge=0)
    manual_edit_count: int | None = Field(default=None, ge=0)
    trend_cluster_id: str | None = None
    # 过程信号（§11 学习信号，VF-603 分析用；均 Optional 向后兼容）：
    human_selected: bool | None = None  # 是否人工选中（vs 自动通过）
    rejected_then_revised: bool | None = None  # 是否经历 驳回→修改 回路
    trend_hotness_at_publish: float | None = Field(default=None, ge=0)  # 发布时热度
    publish_delay_hours: float | None = Field(default=None, ge=0)  # 热点发现→发布延迟


class VideoPerformanceRecord(ContractModel):
    """一条已发布视频的归因事实：特征 + 抓到的表现快照（§10/§11 的输入事实，不可变）。"""

    id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    platform: PublishPlatform
    published_at: datetime
    features: PerformanceFeatures
    snapshots: list[PerformanceSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_platform(self) -> "VideoPerformanceRecord":
        for s in self.snapshots:
            if s.platform != self.platform:
                raise ValueError("快照 platform 必须与记录一致")
        return self


class AccountBaselineEntry(ContractModel):
    """账号在某 (age, metric) 下的基线统计（中位数/分位数/样本数）。样本为空时统计为 null。"""

    age_hours: float = Field(ge=0)
    metric: MetricField
    median: float | None = None
    p25: float | None = None
    p75: float | None = None
    sample_count: int = Field(ge=0)


class AccountBaseline(ContractModel):
    """账号基线（多个 age×metric 条目）——账号内相对指标的分母来源（§11）。"""

    account_id: str = Field(min_length=1)
    platform: PublishPlatform
    generated_at: datetime
    entries: list[AccountBaselineEntry] = Field(default_factory=list)


class PerformanceGroupStat(ContractModel):
    """某分组（维度=值）在某 (age, metric) 下的**账号内相对指标**统计。

    `median_relative` 是组内各视频 `指标/账号基线中位数` 的中位数；`sample_count` 是参与统计的
    （相对值非空）视频数；`enough_samples` 标记是否达到可排序/可信阈值。
    """

    dimension: GroupDimension
    value: str = Field(min_length=1)
    age_hours: float = Field(ge=0)
    metric: MetricField
    sample_count: int = Field(ge=0)
    median_relative: float | None = None
    p25_relative: float | None = None
    p75_relative: float | None = None
    enough_samples: bool


class PerformanceDashboard(ContractModel):
    """一个账号在某 (age, metric) 视角下的效果看板：账号基线 + 各维度分组的相对表现。

    交叉校验：`median_relative` 非空的分组必须有可用的账号基线中位数（否则相对值无从谈起）。
    """

    account_id: str = Field(min_length=1)
    platform: PublishPlatform
    generated_at: datetime
    age_hours: float = Field(ge=0)
    metric: MetricField
    baseline: AccountBaselineEntry
    min_samples: int = Field(ge=1)
    group_stats: list[PerformanceGroupStat] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_relative_needs_baseline(self) -> "PerformanceDashboard":
        has_baseline = self.baseline.median is not None and self.baseline.median != 0
        if not has_baseline:
            for g in self.group_stats:
                if g.median_relative is not None:
                    raise ValueError(
                        "无账号基线中位数时，分组不能有 median_relative"
                        "（必须由 domain.build_dashboard 计算）"
                    )
        return self
