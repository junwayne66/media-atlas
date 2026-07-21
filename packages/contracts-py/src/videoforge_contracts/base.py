from pydantic import BaseModel, ConfigDict, Field

# 当前合同 schema 版本。演进规则见 docs/architecture/31-domain-model-and-workflows.md §8：
# Reader 至少兼容当前与前一版本；升版时旧版本 fixture（tests/fixtures/）必须仍可解析。
CONTRACT_SCHEMA_VERSION = "1"


class ContractModel(BaseModel):
    """所有对外持久化/传输合同的基类：禁止未知字段，强制 schema_version。"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: str = Field(
        default=CONTRACT_SCHEMA_VERSION,
        description="合同 schema 版本；Reader 需兼容当前与前一版本",
    )
