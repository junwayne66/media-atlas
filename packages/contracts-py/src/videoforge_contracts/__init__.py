from videoforge_contracts.artifact import Artifact, MediaProbe, ProducedBy, StorageRef
from videoforge_contracts.base import CONTRACT_SCHEMA_VERSION, ContractModel
from videoforge_contracts.enums import (
    CreationMode,
    ExecutionPolicy,
    HealthState,
    IsolationLevel,
    ProjectStatus,
    ProviderType,
    StorageBackend,
)
from videoforge_contracts.problem import ProblemDetail
from videoforge_contracts.project import Project
from videoforge_contracts.provider import CostModel, ProviderDescriptor, ProviderHealth
from videoforge_contracts.task_envelope import ResourceLimits, TaskEnvelope

# schemas/<name>.schema.json 与顶层合同的对应表（导出与漂移检查共用）
CONTRACTS: dict[str, type[ContractModel]] = {
    "project": Project,
    "artifact": Artifact,
    "task-envelope": TaskEnvelope,
    "provider-descriptor": ProviderDescriptor,
    "problem-detail": ProblemDetail,
}

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACTS",
    "Artifact",
    "ContractModel",
    "CostModel",
    "CreationMode",
    "ExecutionPolicy",
    "HealthState",
    "IsolationLevel",
    "MediaProbe",
    "ProblemDetail",
    "ProducedBy",
    "Project",
    "ProjectStatus",
    "ProviderDescriptor",
    "ProviderHealth",
    "ProviderType",
    "ResourceLimits",
    "StorageBackend",
    "StorageRef",
    "TaskEnvelope",
]
