"""采集 Worker 的平台无关合同（VF-108）。

这里只保存结构化、可脱敏的业务事实。Cookie、Authorization、预签名 URL 和 Profile
路径不得进入任何合同；浏览器/设备凭据只以不透明 handle 存在。
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from videoforge_contracts.base import ContractModel

_FORBIDDEN_SEGMENTS = frozenset(
    {
        "authorization",
        "bearer",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "password",
        "passwd",
        "pwd",
        "secret",
        "secrets",
        "token",
    }
)
_OPAQUE_HANDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


def _key_segments(key: str) -> set[str]:
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key)).lower()
    return set(re.findall(r"[a-z]+", snake))


def _reject_sensitive_keys(value: Any, path: str = "value") -> Any:
    if isinstance(value, dict):
        for key, child in value.items():
            if _key_segments(str(key)) & _FORBIDDEN_SEGMENTS:
                raise ValueError(f"{path}.{key} 是敏感字段，不能进入采集合同")
            _reject_sensitive_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{path}[{index}]")
    return value


class RightsBasis(StrEnum):
    UNKNOWN = "UNKNOWN"
    OWNED = "OWNED"
    LICENSED = "LICENSED"
    USER_PROVIDED = "USER_PROVIDED"
    INTERNAL_APPROVED = "INTERNAL_APPROVED"

    @property
    def permits_acquisition(self) -> bool:
        return self is not RightsBasis.UNKNOWN


class IngestJobType(StrEnum):
    DISCOVERY_SEARCH = "DISCOVERY_SEARCH"
    CONTENT_RESOLVE = "CONTENT_RESOLVE"
    MEDIA_ACQUIRE = "MEDIA_ACQUIRE"
    SESSION_CHECK = "SESSION_CHECK"


class IngestJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    NEED_HUMAN = "NEED_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StageOutcomeStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    EMPTY = "EMPTY"
    RETRYABLE_ERROR = "RETRYABLE_ERROR"
    NEED_HUMAN = "NEED_HUMAN"
    PERMANENT_ERROR = "PERMANENT_ERROR"
    CANCELLED = "CANCELLED"


class SourceProfileStatus(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    READY = "READY"
    BUSY = "BUSY"
    NEED_HUMAN = "NEED_HUMAN"
    DISABLED = "DISABLED"


class SourcePublicMetadata(ContractModel):
    author_platform_id: str | None = None
    author_name: str | None = None
    title: str | None = None
    description: str | None = None
    cover_url: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    published_at: datetime | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stats", "raw_metadata")
    @classmethod
    def metadata_must_not_contain_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_sensitive_keys(value)


class DiscoveryQuery(ContractModel):
    id: str = Field(min_length=1)
    platform: str = Field(pattern=r"^douyin$")
    query_text: str = Field(min_length=1, max_length=200)
    filters: dict[str, Any] = Field(default_factory=dict)
    max_items: int = Field(default=30, ge=1, le=200)
    max_scrolls: int = Field(default=12, ge=1, le=100)
    idle_rounds: int = Field(default=3, ge=1, le=20)
    time_budget_s: int = Field(default=60, ge=1, le=600)
    profile_id: str | None = None
    created_by: str = Field(default="local-user", min_length=1)
    created_at: datetime

    @field_validator("filters")
    @classmethod
    def filters_must_not_contain_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_sensitive_keys(value)


class RightsAttestation(ContractModel):
    id: str = Field(min_length=1)
    source_asset_id: str = Field(min_length=1)
    basis: RightsBasis
    note: str | None = Field(default=None, max_length=1000)
    actor_id: str = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def must_authorize_acquisition(self) -> RightsAttestation:
        if not self.basis.permits_acquisition:
            raise ValueError("UNKNOWN 不能创建媒体获取权利声明")
        return self


class SourceProfile(ContractModel):
    id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    platform: str = Field(pattern=r"^douyin$")
    profile_key: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    credential_handle: str | None = None
    status: SourceProfileStatus = SourceProfileStatus.UNCONFIGURED
    last_verified_at: datetime | None = None
    last_challenge_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("credential_handle")
    @classmethod
    def handle_must_be_opaque(cls, value: str | None) -> str | None:
        if value is not None and not _OPAQUE_HANDLE_RE.fullmatch(value):
            raise ValueError("credential_handle 必须是不含路径/协议语义的不透明引用")
        return value

    @field_validator("metadata")
    @classmethod
    def profile_metadata_must_not_contain_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_sensitive_keys(value)


class StageOutcome(ContractModel):
    status: StageOutcomeStatus
    result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    message: str | None = Field(default=None, max_length=1000)
    retry_after_s: int | None = Field(default=None, ge=1, le=3600)
    debug_artifact_ids: list[str] = Field(default_factory=list)

    @field_validator("result")
    @classmethod
    def result_must_not_contain_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_sensitive_keys(value)

    @model_validator(mode="after")
    def error_outcome_has_code(self) -> StageOutcome:
        if (
            self.status
            in {
                StageOutcomeStatus.RETRYABLE_ERROR,
                StageOutcomeStatus.NEED_HUMAN,
                StageOutcomeStatus.PERMANENT_ERROR,
            }
            and not self.error_code
        ):
            raise ValueError(f"{self.status} 必须携带 error_code")
        return self


class IngestJob(ContractModel):
    id: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    job_type: IngestJobType
    status: IngestJobStatus
    platform: str = Field(pattern=r"^douyin$")
    idempotency_key: str = Field(min_length=1, max_length=200)
    workflow_id: str | None = None
    worker_task_id: str | None = None
    source_asset_id: str | None = None
    discovery_query_id: str | None = None
    profile_id: str | None = None
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=50)
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = Field(default=None, max_length=1000)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime

    @field_validator("payload", "result")
    @classmethod
    def job_data_must_not_contain_secrets(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        return _reject_sensitive_keys(value)


class IngestJobEvent(ContractModel):
    id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1, max_length=100)
    from_status: IngestJobStatus | None = None
    to_status: IngestJobStatus | None = None
    actor_id: str | None = None
    message: str | None = Field(default=None, max_length=1000)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("details")
    @classmethod
    def details_must_not_contain_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_sensitive_keys(value)


__all__ = [
    "DiscoveryQuery",
    "IngestJob",
    "IngestJobEvent",
    "IngestJobStatus",
    "IngestJobType",
    "RightsAttestation",
    "RightsBasis",
    "SourceProfile",
    "SourceProfileStatus",
    "SourcePublicMetadata",
    "StageOutcome",
    "StageOutcomeStatus",
]
