"""各合同的规范有效样例：round-trip 测试与 v1 兼容 fixture 的共同来源。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    Artifact,
    ContractModel,
    CostModel,
    CreationMode,
    MediaProbe,
    ProblemDetail,
    ProducedBy,
    Project,
    ProviderDescriptor,
    ProviderHealth,
    ResourceLimits,
    StorageRef,
    TaskEnvelope,
    TrendCluster,
    TrendItemSnapshot,
    TrendStage,
    TrendSubScores,
)

_T0 = datetime(2026, 7, 21, 8, 0, 0, tzinfo=UTC)


def make_project() -> Project:
    return Project(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7V8",
        title="AI 芯片新品热点二创",
        vertical="ai-tech",
        source_language="zh-CN",
        target_languages=["en-US"],
        creation_mode=CreationMode.STRUCTURE_REWRITE,
        trend_cluster_id="01J2ZK3AC9V6XW8YQ4R5T6U7W0",
        source_asset_ids=["01J2ZK3AC9V6XW8YQ4R5T6U7W1"],
        workflow_id="create-01J2ZK3AC9",
        created_at=_T0,
        updated_at=_T0,
    )


def make_artifact() -> Artifact:
    return Artifact(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7W1",
        project_id="01J2ZK3AC9V6XW8YQ4R5T6U7V8",
        kind="source_video",
        filename="source.mp4",
        mime_type="video/mp4",
        size_bytes=10_485_760,
        sha256="a" * 64,
        media=MediaProbe(duration_s=58.2, fps=30.0, width=1080, height=1920, channels=2),
        produced_by=ProducedBy(activity="ingest.download", tool="yt-dlp", tool_version="2026.06.1"),
        storage=StorageRef(
            backend="s3", bucket="videoforge", object_key="artifacts/t/p/a/source.mp4"
        ),
        created_at=_T0,
    )


def make_task_envelope() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="01J2ZK3AC9V6XW8YQ4R5T6U7W2",
        idempotency_key="probe-01J2ZK3AC9-1",
        capability="media.probe",
        attempt=1,
        input_artifact_ids=["01J2ZK3AC9V6XW8YQ4R5T6U7W1"],
        params={"target": "full", "sample_rate": 1},
        resource_limits=ResourceLimits(cpu_cores=2.0, memory_mb=2048, timeout_s=600),
        credential_handles=["ch-9f2e"],
        created_at=_T0,
    )


def make_provider_descriptor() -> ProviderDescriptor:
    return ProviderDescriptor(
        name="asr.whisper-cpp",
        provider_type="ASRProvider",
        version="0.1.0",
        capabilities=["asr.transcribe"],
        execution_location="local",
        languages=["zh-CN", "en-US"],
        cost_model=CostModel(unit="second", estimated_cost_per_unit=0.0),
        health=ProviderHealth(status="healthy", last_success_at=_T0),
    )


def make_problem_detail() -> ProblemDetail:
    return ProblemDetail(
        type="https://videoforge.dev/problems/connector-rate-limited",
        title="Connector rate limited",
        status=429,
        code="RATE_LIMITED",
        detail="tiktok discovery connector 触发限流",
        retryable=True,
        correlation_id="cor_01J2ZK3AC9",
        context={"provider": "tiktok.discovery", "attempt": 2},
    )


def make_trend_item_snapshot() -> TrendItemSnapshot:
    return TrendItemSnapshot(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7X0",
        observed_at=_T0,
        platform="douyin",
        region="CN",
        locale="zh-CN",
        item_id="dy-7412",
        author_id="dy-author-9",
        published_at=_T0,
        views=120000,
        likes=8400,
        comments=610,
        shares=1200,
        saves=None,  # 未采到，保留 null 不填 0
        followers_at_observation=52000,
        rank=7,
        hashtag_ids=["ai", "m5-chip"],
        sound_id="snd-33",
        raw_artifact_id="01J2ZK3AC9V6XW8YQ4R5T6U7X1",
        collector_version="douyin-collector@0.1.0",
        source_confidence=0.9,
    )


def make_trend_cluster() -> TrendCluster:
    return TrendCluster(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7X2",
        title="新一代 AI 芯片发布",
        canonical_topic="ai-chip-launch-2026",
        keywords=["AI 芯片", "M5", "端侧推理"],
        entities=["Apple", "M5"],
        member_item_ids=["dy-7412", "tt-9981"],
        snapshot_ids=["01J2ZK3AC9V6XW8YQ4R5T6U7X0"],
        first_seen_at=_T0,
        last_seen_at=_T0,
        stage=TrendStage.RISING,
        sub_scores=TrendSubScores(
            velocity=0.7,
            acceleration=0.6,
            engagement_efficiency=0.4,
            cross_platform_score=0.8,
            topic_fit=0.9,
            novelty=0.5,
            source_quality=0.6,
            saturation=0.2,
            decay=0.0,
        ),
        hot_score=0.68,
        weights_version="v1",
        reason_codes=["HIGH_ACCELERATION", "CROSS_PLATFORM", "STRONG_TOPIC_FIT"],
        embedding_ref="emb-cluster-1",
        source_confidence=0.85,
        vertical="ai-tech",
        created_at=_T0,
        updated_at=_T0,
    )


SAMPLES: dict[str, ContractModel] = {
    "project": make_project(),
    "artifact": make_artifact(),
    "task-envelope": make_task_envelope(),
    "provider-descriptor": make_provider_descriptor(),
    "problem-detail": make_problem_detail(),
    "trend-item-snapshot": make_trend_item_snapshot(),
    "trend-cluster": make_trend_cluster(),
}
