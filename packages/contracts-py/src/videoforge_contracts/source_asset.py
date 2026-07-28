"""来源素材聚合合同（docs/modules/41 §2/§3，补齐 VF-105/VF-107 的持久化面）。

一条 SourceAsset 记录「用户想导入的一份原始素材」及其**可解释的处置**：

- IMPORTED：本地已有原片（file_sha256 已算），可进入分析链。
- MANUAL_FALLBACK：链接已解析，但实时下载未配置/失败 → 请人工下载后关联本地文件。
- NEEDS_EXPANSION：短链，需先展开（展开需网络，默认未启用，53 §10 停止条件）。
- UNRESOLVABLE：输入无法识别出平台/内容 ID。

处置必须可解释：`reason` 恒非空、失败/未配置另带 `error_code`；空板/静默失败是被禁止的
（40 §9/§10 的同一立场在获取侧的延续）。

**红线（README §4）：本合同结构上不含任何 cookie/token/凭据字段。** Cookie 只以不透明
`credential_handle` 存在于下载请求内部，绝不进入持久化的素材记录；`AcquisitionAttemptSummary`
只留 provider 名 + 状态 + 错误码，不存下载器返回的原始元数据。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.ingest import RightsBasis, SourcePublicMetadata

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class SourceAssetKind(StrEnum):
    URL = "URL"  # 来自链接/分享文本
    LOCAL_FILE = "LOCAL_FILE"  # 手工导入的本地原片（始终可用的兜底路径）


class SourceDisposition(StrEnum):
    """素材当前处置。四态互斥，且都能对用户解释「下一步做什么」。"""

    IMPORTED = "IMPORTED"  # 本地已有文件，可分析
    MANUAL_FALLBACK = "MANUAL_FALLBACK"  # 已解析但未能自动获取 → 人工下载后关联
    NEEDS_EXPANSION = "NEEDS_EXPANSION"  # 短链待展开
    UNRESOLVABLE = "UNRESOLVABLE"  # 无法识别平台/内容 ID
    METADATA_ONLY = "METADATA_ONLY"  # 已保存公开元数据，尚未授权/获取原始媒体


class AcquisitionAttemptSummary(ContractModel):
    """一次下载尝试的摘要（DownloadRouter attempts 轨迹的持久化形态）。

    只留「谁试了、结果如何」——不存下载器的原始元数据，更不可能带 Cookie/Token。
    """

    connector: str = Field(min_length=1, description="下载连接器名，如 download.f2")
    status: str = Field(min_length=1, description="DownloadStatus 值，如 unconfigured")
    error_code: str | None = Field(default=None, description="AcquisitionErrorCode 值")


class AcquisitionSummary(ContractModel):
    """获取过程的可重放摘要（README §4：工具版本 + 输出哈希 + 可解释尝试轨迹）。"""

    tool_name: str = Field(min_length=1, description="最终/路由使用的工具或连接器名")
    tool_version: str | None = Field(default=None, description="工具版本；未配置时为 null")
    output_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    attempts: list[AcquisitionAttemptSummary] = Field(default_factory=list)
    manual_fallback: bool = Field(default=False, description="链耗尽 → 应转手工导入")


class SourceAsset(ContractModel):
    """来源素材聚合（可版本化：version 乐观锁）。"""

    id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1, description="乐观并发版本")
    kind: SourceAssetKind
    original_input: str = Field(min_length=1, description="用户粘贴的原文/路径，保留 provenance")
    platform: str = Field(
        default="unknown", min_length=1, description="douyin/tiktok/youtube/manual/unknown"
    )
    content_id: str | None = None
    canonical_url: str | None = None
    disposition: SourceDisposition
    reason: str = Field(min_length=1, description="处置理由（面向人的可解释说明）")
    error_code: str | None = Field(default=None, description="失败/未配置时的结构化错误码")
    local_path: str | None = None
    file_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    acquisition: AcquisitionSummary | None = None
    public_metadata: SourcePublicMetadata | None = None
    rights_basis: RightsBasis = RightsBasis.UNKNOWN
    rights_attestation_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    discovered_at: datetime | None = None
    last_seen_at: datetime | None = None
    project_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _check_disposition_consistency(self) -> "SourceAsset":
        # IMPORTED 必须真有本地文件的哈希——否则「已导入」是空话，下游分析会拿不到输入
        if (
            self.disposition is SourceDisposition.IMPORTED
            and not self.file_sha256
            and not self.artifact_ids
        ):
            raise ValueError("IMPORTED 必须携带 file_sha256 或 artifact_ids（否则并未真正导入）")
        # 不可解析必须带错误码，保证 UI 能给出结构化提示而非空白
        if self.disposition is SourceDisposition.UNRESOLVABLE and not self.error_code:
            raise ValueError("UNRESOLVABLE 必须携带 error_code")
        if (
            self.discovered_at is not None
            and self.last_seen_at is not None
            and self.last_seen_at < self.discovered_at
        ):
            raise ValueError("last_seen_at 不能早于 discovered_at")
        return self


__all__ = [
    "AcquisitionAttemptSummary",
    "AcquisitionSummary",
    "SourceAsset",
    "SourceAssetKind",
    "SourceDisposition",
]
