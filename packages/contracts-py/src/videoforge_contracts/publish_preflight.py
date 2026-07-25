"""发布前检查合同（docs/modules/44 §3 连接器能力 + 预检；§9 元数据规则）。

VF-502 目标：**发布前检查（Preflight）**——把渲染好的 Package 对照平台规则集
（分辨率/宽高比/编码/容器/文件大小/时长/标题标签长度/禁用字符）+ 连接器**上报的能力
和授权/审核/账号状态**逐项检查，**发布前**给出可发布结论。

**红线**：Connector **返回能力，不由 UI 猜测**（§3）；未授权/审核未过/账号异常必须在预检
明示（§3.1/§3.2），不静默放行。真实发布（上传/Direct Post）是 VF-503 起的 stop-condition，
本层只做**只读预检 + 能力上报**，不触真实平台。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.review_policy import ReviewSeverity


class PublishPlatform(StrEnum):
    TIKTOK = "TIKTOK"
    DOUYIN = "DOUYIN"


class PublishMethod(StrEnum):
    """§3 发布连接器优先级阶梯。"""

    OFFICIAL_API = "OFFICIAL_API"
    OFFICIAL_SHARE_SDK = "OFFICIAL_SHARE_SDK"
    BROWSER_AUTOMATION = "BROWSER_AUTOMATION"
    ANDROID_DEVICE = "ANDROID_DEVICE"
    MANUAL_EXPORT = "MANUAL_EXPORT"


class AuthStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    PENDING_REVIEW = "PENDING_REVIEW"  # 授权申请审核中
    UNAUTHORIZED = "UNAUTHORIZED"
    EXPIRED = "EXPIRED"


class ClientReviewStatus(StrEnum):
    """§3.1 客户端/应用审核状态（未审核 → 可见性受限）。"""

    APPROVED = "APPROVED"
    UNDER_REVIEW = "UNDER_REVIEW"
    UNAUDITED = "UNAUDITED"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RESTRICTED = "RESTRICTED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class PreflightCheck(StrEnum):
    RESOLUTION = "RESOLUTION"
    ASPECT_RATIO = "ASPECT_RATIO"
    VIDEO_CODEC = "VIDEO_CODEC"
    AUDIO_CODEC = "AUDIO_CODEC"
    CONTAINER = "CONTAINER"
    FILE_SIZE = "FILE_SIZE"
    DURATION = "DURATION"
    TITLE_LENGTH = "TITLE_LENGTH"
    TITLE_BANNED_CHARS = "TITLE_BANNED_CHARS"
    DESCRIPTION_LENGTH = "DESCRIPTION_LENGTH"
    TAG_COUNT = "TAG_COUNT"
    TAG_LENGTH = "TAG_LENGTH"
    AUTH_STATUS = "AUTH_STATUS"
    REVIEW_STATUS = "REVIEW_STATUS"
    ACCOUNT_STATUS = "ACCOUNT_STATUS"
    METHOD_UNAVAILABLE = "METHOD_UNAVAILABLE"


class PlatformPublishSpec(ContractModel):
    """平台发布规则集（数据化 §3.1/§3.2/§9 约束，可按平台/账号覆盖）。"""

    platform: PublishPlatform
    allowed_aspect_ratios: list[str] = Field(min_length=1)  # 如 "9:16"
    min_width: int = Field(gt=0)
    min_height: int = Field(gt=0)
    max_width: int = Field(gt=0)
    max_height: int = Field(gt=0)
    allowed_video_codecs: list[str] = Field(min_length=1)
    allowed_audio_codecs: list[str] = Field(min_length=1)
    allowed_containers: list[str] = Field(min_length=1)
    max_file_size_bytes: int = Field(gt=0)
    min_duration_ms: int = Field(ge=0)
    max_duration_ms: int = Field(gt=0)
    title_max_len: int = Field(gt=0)
    description_max_len: int = Field(ge=0)
    max_tags: int = Field(ge=0)
    tag_max_len: int = Field(gt=0)
    banned_title_chars: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_bounds(self) -> "PlatformPublishSpec":
        if self.min_width > self.max_width:
            raise ValueError("min_width 必须 ≤ max_width")
        if self.min_height > self.max_height:
            raise ValueError("min_height 必须 ≤ max_height")
        if self.min_duration_ms > self.max_duration_ms:
            raise ValueError("min_duration_ms 必须 ≤ max_duration_ms")
        return self


class PublishMediaProbe(ContractModel):
    """渲染成片的媒体事实（预检输入；非顶层注册）。"""

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    aspect_ratio: str = Field(min_length=1)
    video_codec: str = Field(min_length=1)
    audio_codec: str = Field(min_length=1)
    container: str = Field(min_length=1)
    file_size_bytes: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class PublishMetadata(ContractModel):
    """发布元数据（§9；批准后冻结，Adapter 不得自改——本层只校验）。"""

    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    language: str = Field(min_length=1)
    cover_ref: str | None = None


class PublishConnectorCapability(ContractModel):
    """连接器上报的能力 + 授权/审核/账号状态（§3 "Connector 返回能力，不由 UI 猜"）。"""

    platform: PublishPlatform
    method: PublishMethod
    available: bool = Field(description="该方法当前是否可用")
    direct_post: bool = False
    auth_status: AuthStatus
    client_review_status: ClientReviewStatus = ClientReviewStatus.APPROVED
    account_status: AccountStatus
    supported_containers: list[str] = Field(default_factory=list)
    max_file_size_bytes: int | None = Field(default=None, gt=0)
    notes: str | None = None


class PreflightFinding(ContractModel):
    check: PreflightCheck
    severity: ReviewSeverity
    detail: str = Field(min_length=1)
    evidence: dict[str, object] = Field(default_factory=dict)


class PreflightReport(ContractModel):
    """发布前检查报告。`publishable` 必须由 domain 计算；交叉校验拒绝 publishable=True
    与任何 ERROR/FATAL 发现并存（手工报告骗不过发布前门）。"""

    id: str = Field(min_length=1)
    platform: PublishPlatform
    method: PublishMethod
    findings: list[PreflightFinding] = Field(default_factory=list)
    publishable: bool
    created_at: datetime

    @model_validator(mode="after")
    def _check_gate(self) -> "PreflightReport":
        if self.publishable and any(
            f.severity in (ReviewSeverity.ERROR, ReviewSeverity.FATAL) for f in self.findings
        ):
            raise ValueError(
                "publishable=True 不能与 ERROR/FATAL 发现并存"
                "（必须调用 domain.run_preflight / validate_preflight_gate 计算）"
            )
        return self
