from typing import Any

from pydantic import ConfigDict, Field

from videoforge_contracts.base import ContractModel


class ProblemDetail(ContractModel):
    """RFC 9457 Problem Details；API 错误统一格式（docs/implementation/51 §2）。允许扩展字段。

    禁止把栈、Cookie、Token、完整外部响应放进任何字段返回给客户端。
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(default="about:blank", description="问题类型 URI")
    title: str = Field(min_length=1)
    status: int = Field(ge=100, le=599)
    code: str | None = Field(
        default=None, description="机器可读错误码，如 PROVIDER_TIMEOUT（51 §2/§12）"
    )
    detail: str | None = None
    instance: str | None = Field(default=None, description="本次出错请求的 URI/引用")
    retryable: bool | None = Field(default=None, description="调用方是否值得原样重试")
    correlation_id: str | None = Field(default=None, description="跨服务关联 id，如 cor_...")
    context: dict[str, Any] | None = Field(
        default=None, description="结构化上下文，如 {provider, attempt}"
    )
