"""各合同的规范有效样例：round-trip 测试与 v1 兼容 fixture 的共同来源。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    Artifact,
    BBox,
    ContractModel,
    CostModel,
    CreationMode,
    FrameAnalysis,
    FrameSampleReason,
    MediaProbe,
    ProblemDetail,
    ProducedBy,
    Project,
    ProviderDescriptor,
    ProviderHealth,
    ResourceLimits,
    StorageRef,
    TaskEnvelope,
    TextObservation,
    TextTrack,
    TextTrackKind,
    TextTrackSet,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
    TranscriptWord,
    TrendCluster,
    TrendItemSnapshot,
    TrendStage,
    TrendSubScores,
    VisualAnalysis,
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


def make_transcript() -> Transcript:
    return Transcript(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7Y0",
        source_artifact_id="01J2ZK3AC9V6XW8YQ4R5T6U7W1",
        language="zh-CN",
        segments=[
            TranscriptSegment(
                id="seg-0",
                start_ms=120,
                end_ms=2480,
                speaker_id="spk_0",
                language="zh-CN",
                text="今天带大家拆解这款 AI 芯片",
                confidence=0.93,
                words=[
                    TranscriptWord(text="今天", start_ms=120, end_ms=520, confidence=0.95),
                    TranscriptWord(text="AI", start_ms=1400, end_ms=1720, confidence=0.55,
                                   low_confidence=True),
                    TranscriptWord(text="芯片", start_ms=1720, end_ms=2480, confidence=0.9),
                ],
            ),
            TranscriptSegment(
                id="seg-1",
                start_ms=2600,
                end_ms=4200,
                speaker_id="spk_0",
                language="en-US",
                text="on device inference",
                confidence=0.88,
                words=[],
            ),
        ],
        models=TranscriptModels(
            asr_provider="asr.whisperx",
            asr_model="large-v3",
            asr_version="3.1.1",
            vad_version="silero-4.0",
            align_version="wav2vec2-zh",
            speaker_version="pyannote-3.1",
        ),
        hotwords=["M5", "端侧推理"],
        duration_ms=58200,
        created_at=_T0,
    )


def make_text_track_set() -> TextTrackSet:
    return TextTrackSet(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7Z0",
        source_artifact_id="01J2ZK3AC9V6XW8YQ4R5T6U7W1",
        ocr_provider="ocr.paddle",
        ocr_version="2.7",
        tracks=[
            TextTrack(
                id="tt-0",
                kind=TextTrackKind.CAPTION,
                text="端侧推理很快",
                start_ms=1200,
                end_ms=3600,
                confidence=0.91,
                motion="STATIC",
                observations=[
                    TextObservation(
                        frame_time_ms=1200,
                        bbox=BBox(x=0.2, y=0.82, w=0.6, h=0.08),
                        text="端侧推理很快",
                        confidence=0.9,
                    ),
                    TextObservation(
                        frame_time_ms=2400,
                        bbox=BBox(x=0.21, y=0.82, w=0.6, h=0.08),
                        text="端侧推理很快",
                        confidence=0.92,
                    ),
                ],
            ),
            TextTrack(
                id="tt-1",
                kind=TextTrackKind.BRAND_MARK,
                text="@创作者",
                start_ms=0,
                end_ms=58000,
                confidence=0.8,
                motion="STATIC",
                style_hint="watermark",
                observations=[
                    TextObservation(
                        frame_time_ms=0,
                        bbox=BBox(x=0.82, y=0.05, w=0.14, h=0.05),
                        text="@创作者",
                        confidence=0.8,
                        occluded=False,
                    )
                ],
            ),
        ],
        created_at=_T0,
    )


def make_visual_analysis() -> VisualAnalysis:
    return VisualAnalysis(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZA",
        source_artifact_id="01J2ZK3AC9V6XW8YQ4R5T6U7W1",
        sampling_policy="representative@v1",
        vlm_provider="vlm.qwen_vl",
        vlm_version="max-0809",
        frames=[
            FrameAnalysis(
                frame_time_ms=0,
                reasons=[FrameSampleReason.KEYFRAME],
                caption="创作者出镜，桌面摆放芯片开发板",
                labels=["person", "product", "desk"],
                confidence=0.9,
            ),
            FrameAnalysis(
                frame_time_ms=3000,
                reasons=[FrameSampleReason.SCENE_CUT, FrameSampleReason.TEXT_CHANGE],
                caption="屏幕录制：跑分图表",
                labels=["screen_record", "chart"],
                confidence=0.86,
            ),
            FrameAnalysis(
                frame_time_ms=8000,
                reasons=[FrameSampleReason.LOW_CONFIDENCE],
                caption=None,  # 已选中，尚未分析
                labels=[],
            ),
        ],
        created_at=_T0,
    )


SAMPLES: dict[str, ContractModel] = {
    "project": make_project(),
    "artifact": make_artifact(),
    "task-envelope": make_task_envelope(),
    "provider-descriptor": make_provider_descriptor(),
    "problem-detail": make_problem_detail(),
    "trend-item-snapshot": make_trend_item_snapshot(),
    "trend-cluster": make_trend_cluster(),
    "transcript": make_transcript(),
    "text-track-set": make_text_track_set(),
    "visual-analysis": make_visual_analysis(),
}
