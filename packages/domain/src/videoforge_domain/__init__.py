from videoforge_domain.blueprint import (
    BlueprintIssue,
    BlueprintIssueKind,
    build_candidate_rhetorical_beats,
    build_visual_beats,
    coverage_ratio,
    is_valid_blueprint,
    validate_blueprint,
)
from videoforge_domain.cluster_scoring import compute_sub_scores, rescore_cluster
from videoforge_domain.dedup import (
    AssetFingerprint,
    DedupConfig,
    DuplicateGroup,
    DuplicateLayer,
    DuplicateMatch,
    find_duplicate_groups,
)
from videoforge_domain.errors import DomainError, InsufficientSnapshots
from videoforge_domain.fingerprints import (
    dhash_from_gray,
    hamming,
    hamming_similarity,
    phash_sequence_similarity,
    text_simhash,
)
from videoforge_domain.frame_sampling import SAMPLING_POLICY, select_representative_frames
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
from videoforge_domain.texttrack import (
    classify_kind,
    iou,
    track_text_observations,
    vote_text,
)
from videoforge_domain.transcript import (
    low_confidence_spans,
    mark_low_confidence,
    needs_review,
)

__all__ = [
    "ENGAGEMENT_METRICS",
    "SAMPLING_POLICY",
    "STAGE_TRANSITIONS",
    "AssetFingerprint",
    "BlueprintIssue",
    "BlueprintIssueKind",
    "DedupConfig",
    "DomainError",
    "DuplicateGroup",
    "DuplicateLayer",
    "DuplicateMatch",
    "IllegalStageTransition",
    "InsufficientSnapshots",
    "assert_transition",
    "build_candidate_rhetorical_beats",
    "build_visual_beats",
    "can_transition",
    "classify_kind",
    "classify_stage",
    "compute_sub_scores",
    "coverage_ratio",
    "decline_from_peak",
    "derive_reason_codes",
    "dhash_from_gray",
    "engagement_efficiency",
    "find_duplicate_groups",
    "hamming",
    "hamming_similarity",
    "hot_score",
    "iou",
    "is_valid_blueprint",
    "low_confidence_spans",
    "mark_low_confidence",
    "needs_review",
    "normalize_rate",
    "phash_sequence_similarity",
    "rescore_cluster",
    "select_representative_frames",
    "series_acceleration",
    "series_velocity",
    "sigmoid",
    "text_simhash",
    "track_text_observations",
    "validate_blueprint",
    "vote_text",
]
