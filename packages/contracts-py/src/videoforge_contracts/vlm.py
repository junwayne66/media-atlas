"""视觉分析合同（docs/modules/41 §9/§10.1）。

VLM 只分析「代表帧」——由 domain.select_representative_frames 从场景切点/文本轨/说话人/
低置信片段选出的一小撮帧，绝不逐帧云调用（成本红线）。FrameAnalysis.caption 为 null 表示
「已选中但尚未经 VLM 分析」；VLM Provider 批量回填 caption/labels。
"""

from datetime import datetime

from pydantic import Field

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import FrameSampleReason


class FrameAnalysis(ContractModel):
    """一帧代表帧：为何被选 + （分析后的）VLM 输出。"""

    frame_time_ms: int = Field(ge=0)
    reasons: list[FrameSampleReason] = Field(min_length=1, description="被选中的原因（可多个）")
    caption: str | None = Field(default=None, description="VLM 描述；null=尚未分析")
    labels: list[str] = Field(default_factory=list, description="VLM 标签：人物/屏录/产品/图卡等")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class VisualAnalysis(ContractModel):
    """一次视觉分析：代表帧集 + （可选）VLM provider/版本 + 采样策略。可重放。"""

    id: str = Field(min_length=1)
    source_artifact_id: str | None = None
    frames: list[FrameAnalysis] = Field(default_factory=list)
    sampling_policy: str = Field(min_length=1, description="选帧策略标识，如 representative@v1")
    vlm_provider: str | None = Field(default=None, description="null=仅选帧未分析")
    vlm_version: str | None = None
    created_at: datetime
