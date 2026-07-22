from videoforge_contracts.artifact import Artifact, MediaProbe, ProducedBy, StorageRef
from videoforge_contracts.base import CONTRACT_SCHEMA_VERSION, ContractModel
from videoforge_contracts.enums import (
    CreationMode,
    ExecutionPolicy,
    FrameSampleReason,
    HealthState,
    IsolationLevel,
    ProjectStatus,
    ProviderType,
    StorageBackend,
    TextTrackKind,
    TrendStage,
)
from videoforge_contracts.problem import ProblemDetail
from videoforge_contracts.project import Project
from videoforge_contracts.provider import CostModel, ProviderDescriptor, ProviderHealth
from videoforge_contracts.task_envelope import ResourceLimits, TaskEnvelope
from videoforge_contracts.texttrack import (
    BBox,
    TextObservation,
    TextTrack,
    TextTrackSet,
)
from videoforge_contracts.transcript import (
    Transcript,
    TranscriptModels,
    TranscriptSegment,
    TranscriptWord,
)
from videoforge_contracts.trend import (
    HotScoreWeights,
    TrendCluster,
    TrendItemSnapshot,
    TrendSubScores,
)
from videoforge_contracts.vlm import FrameAnalysis, VisualAnalysis

# schemas/<name>.schema.json 与顶层合同的对应表（导出与漂移检查共用）
CONTRACTS: dict[str, type[ContractModel]] = {
    "project": Project,
    "artifact": Artifact,
    "task-envelope": TaskEnvelope,
    "provider-descriptor": ProviderDescriptor,
    "problem-detail": ProblemDetail,
    "trend-item-snapshot": TrendItemSnapshot,
    "trend-cluster": TrendCluster,
    "transcript": Transcript,
    "text-track-set": TextTrackSet,
    "visual-analysis": VisualAnalysis,
}

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACTS",
    "Artifact",
    "BBox",
    "ContractModel",
    "CostModel",
    "CreationMode",
    "ExecutionPolicy",
    "FrameAnalysis",
    "FrameSampleReason",
    "HealthState",
    "HotScoreWeights",
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
    "TextObservation",
    "TextTrack",
    "TextTrackKind",
    "TextTrackSet",
    "Transcript",
    "TranscriptModels",
    "TranscriptSegment",
    "TranscriptWord",
    "TrendCluster",
    "TrendItemSnapshot",
    "TrendStage",
    "TrendSubScores",
    "VisualAnalysis",
]
