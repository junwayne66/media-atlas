from datetime import datetime

from pydantic import Field

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import StorageBackend


class MediaProbe(ContractModel):
    """探测出的媒体技术属性（可选，非媒体 Artifact 无此段）。"""

    duration_s: float | None = Field(default=None, ge=0)
    fps: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)
    codec: str | None = None
    time_base: str | None = Field(default=None, description="如 1/30000")


class ProducedBy(ContractModel):
    """生成来源：Activity、工具与模型版本（可重放性要求）。"""

    activity: str | None = None
    tool: str | None = None
    tool_version: str | None = None
    model: str | None = None


class StorageRef(ContractModel):
    """存储位置。对象键不承载业务真值（docs/architecture/30 §7）。"""

    backend: StorageBackend
    bucket: str | None = None
    object_key: str | None = None
    local_path: str | None = None


class Artifact(ContractModel):
    """不可变产物记录（docs/architecture/30 §7）。同哈希可去重，来源记录不得合并丢失。"""

    id: str = Field(min_length=1, description="UUIDv7/ULID")
    project_id: str | None = None
    kind: str = Field(min_length=1, description="如 source_video / proxy / render / analysis")
    filename: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    phash: str | None = Field(default=None, description="视频感知哈希")
    ahash: str | None = Field(default=None, description="均值哈希（docs/architecture/30 §7）")
    audio_fingerprint: str | None = None
    media: MediaProbe | None = None
    upstream_artifact_ids: list[str] = Field(default_factory=list)
    produced_by: ProducedBy | None = None
    storage: StorageRef
    retention_policy: str | None = None
    sensitivity: str | None = Field(default=None, description="敏感级别标记")
    created_at: datetime
