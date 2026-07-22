from videoforge_domain.cluster_scoring import compute_sub_scores, rescore_cluster
from videoforge_domain.errors import DomainError, InsufficientSnapshots
from videoforge_domain.kinematics import (
    ENGAGEMENT_METRICS,
    decline_from_peak,
    engagement_efficiency,
    series_acceleration,
    series_velocity,
)
from videoforge_domain.reason_codes import derive_reason_codes
from videoforge_domain.scoring import hot_score, normalize_rate, sigmoid
from videoforge_domain.staging import (
    STAGE_TRANSITIONS,
    IllegalStageTransition,
    assert_transition,
    can_transition,
    classify_stage,
)

__all__ = [
    "ENGAGEMENT_METRICS",
    "STAGE_TRANSITIONS",
    "DomainError",
    "IllegalStageTransition",
    "InsufficientSnapshots",
    "assert_transition",
    "can_transition",
    "classify_stage",
    "compute_sub_scores",
    "decline_from_peak",
    "derive_reason_codes",
    "engagement_efficiency",
    "hot_score",
    "normalize_rate",
    "rescore_cluster",
    "series_acceleration",
    "series_velocity",
    "sigmoid",
]
