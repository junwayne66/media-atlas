"""QA 检测合同（docs/modules/42 §11）。

发布前的最后一道门：把渲染成品与源 Timeline 比对，把黑帧/冻帧/频闪/字幕安全区/响度/时长
一致性等落成结构化 QAFinding；BLOCKER 一处即拒发布，MAJOR 超阈值升级为拒。

真实检测器（ebur128 / opencv / VLM）属停止条件延后 —— 本合同族只定义 QAReport 结构，规则引擎
与阈值门在纯域，供 provider-sdk MediaAnalyzerProvider 接入真实检测器时消费。
"""

from datetime import datetime

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import QAFindingKind, QASeverity


class QAFinding(ContractModel):
    """单条 QA 发现：位置 + 类别 + 严重级 + 证据键值对。"""

    id: str = Field(min_length=1)
    kind: QAFindingKind
    severity: QASeverity
    at_ms: int = Field(ge=0, description="发生时刻（输出时间线）")
    duration_ms: int = Field(default=0, ge=0, description="持续时长；0 表示瞬时事件")
    track_ref: str | None = Field(default=None, description="所属轨道 id，如 v1/a0/v4")
    detail: str | None = Field(default=None, description="可读描述")
    evidence: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="度量证据，如 {mean_luma: 3.2, threshold: 8}"
    )


class QAReport(ContractModel):
    """一次渲染的 QA 报告：全部发现 + 时长一致性 + 发布门结论。"""

    id: str = Field(min_length=1)
    timeline_id: str = Field(min_length=1)
    render_manifest_id: str | None = Field(default=None, description="§11 关联 RenderManifest")
    findings: list[QAFinding] = Field(default_factory=list)
    timeline_duration_ms: int = Field(ge=0, description="Timeline 声明的总时长")
    measured_duration_ms: int = Field(ge=0, description="渲染成品实测总时长（ffprobe）")
    # 发布门：True 允许发布，False 拒。domain 计算后写入；本层加交叉校验防手工 report 撒谎。
    pass_or_block: bool = Field(default=True)
    created_at: datetime

    @model_validator(mode="after")
    def _validate_integrity(self) -> "QAReport":
        seen: set[str] = set()
        has_blocker = False
        for f in self.findings:
            if f.id in seen:
                raise ValueError(f"findings 中 id 重复：{f.id}")
            seen.add(f.id)
            if f.severity is QASeverity.BLOCKER:
                has_blocker = True
        # 交叉校验：只要有 BLOCKER，pass_or_block 必须为 False——手工 report 不得声称通过
        if has_blocker and self.pass_or_block:
            raise ValueError(
                "pass_or_block=True 与 BLOCKER finding 冲突；用 validate_publish_gate 计算"
            )
        return self
