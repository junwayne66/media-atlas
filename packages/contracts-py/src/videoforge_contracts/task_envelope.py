import re
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from videoforge_contracts.base import ContractModel
from videoforge_contracts.enums import ExecutionPolicy

# Task Envelope 内禁止出现明文凭据（docs/architecture/30 §5）：
# 平台密码/Cookie 一律走短期 credential_handle，由桌面 Credential Broker 解封。
#
# 键名启发式按"分段精确匹配"实现：access_token / accessToken / Set-Cookie 被拒，
# 而 max_tokens / tokenizer 这类 LLM 参数不受误伤（复数 tokens 有意不在名单内）。
# 已知边界（保持"疑似"定位，不追求完备）：值内夹带（"note": "password=..."）、
# 同形异码字符、拆词键名不会被本校验器捕获；接收端二次校验与 Secret 扫描是后续防线。
_FORBIDDEN_KEY_SEGMENTS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "cookie",
        "cookies",
        "secret",
        "secrets",
        "credential",
        "credentials",
        "token",
        "bearer",
        "authorization",
    }
)


def _key_segments(key: str) -> set[str]:
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key)).lower()
    return set(re.findall(r"[a-z]+", snake))


def _scan_forbidden_keys(value: Any, path: str = "params") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if _key_segments(str(key)) & _FORBIDDEN_KEY_SEGMENTS:
                found.append(f"{path}.{key}")
            found.extend(_scan_forbidden_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            found.extend(_scan_forbidden_keys(child, f"{path}[{i}]"))
    return found


class ResourceLimits(ContractModel):
    cpu_cores: float | None = Field(default=None, gt=0)
    memory_mb: int | None = Field(default=None, gt=0)
    gpu: bool | None = None
    timeout_s: int = Field(gt=0, description="单次尝试的硬超时")


class TaskEnvelope(ContractModel):
    """Worker 领取的任务信封（docs/architecture/30 §5 Task Lease 协议）。"""

    task_id: str = Field(min_length=1)
    idempotency_key: str = Field(
        min_length=1, description="重复提交按 task_id + output_digest 幂等"
    )
    capability: str = Field(min_length=1, description="能力标识，如 media.probe / asr.transcribe")
    attempt: int = Field(ge=1)
    execution_policy: ExecutionPolicy = ExecutionPolicy.LOCAL_PREFERRED
    workflow_id: str | None = None
    lease_id: str | None = None
    lease_expires_at: datetime | None = None
    input_artifact_ids: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="能力专属参数；禁止任何明文凭据字段（用 credential_handles）",
    )
    output_schema_ref: str | None = Field(
        default=None, description="产物需满足的 schema 引用，如 schemas/artifact.schema.json"
    )
    resource_limits: ResourceLimits | None = None
    credential_handles: list[str] = Field(
        default_factory=list, description="短期凭据句柄（非凭据本体）"
    )
    priority: int = Field(default=0, ge=-100, le=100)
    created_at: datetime

    @field_validator("params")
    @classmethod
    def params_must_not_carry_credentials(cls, value: dict[str, Any]) -> dict[str, Any]:
        found = _scan_forbidden_keys(value)
        if found:
            raise ValueError(
                "params 疑似携带明文凭据字段: " + ", ".join(found) + "；请改用 credential_handles"
            )
        return value
