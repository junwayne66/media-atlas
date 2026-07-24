"""各合同的规范有效样例：round-trip 测试与 v1 兼容 fixture 的共同来源。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    AccountStatus,
    Artifact,
    AssetLicense,
    AssetLicenseType,
    AssetPlan,
    AssetPlanSlot,
    AssetRole,
    AssetSource,
    AudioMixPlan,
    AudioMixTrack,
    AudioMixTrackKind,
    AuthStatus,
    BBox,
    BeatSlot,
    BeatTemplate,
    BriefHook,
    CanonicalScript,
    CanonicalSentence,
    Claim,
    ClaimDiff,
    ClaimSourceStatus,
    ClaimTable,
    ClaimTableEntry,
    CleanPlateMethod,
    CleanPlateRequest,
    ClientReviewStatus,
    CompositionSpec,
    ContinuityNote,
    ContinuityRuleKind,
    ContractModel,
    CostModel,
    CreationMode,
    CreativeBrief,
    CreativeOpportunity,
    CreativeTimeline,
    DuckingPolicy,
    DuckingSidechain,
    DurationFitDecision,
    DurationFitPlan,
    DurationFitStatus,
    DurationFitStrategy,
    EditOp,
    EditOpKind,
    EvidenceSpan,
    ExportEntry,
    ExporterKind,
    ExporterReport,
    ExporterStatus,
    FfmpegRenderGraph,
    FilterGraph,
    FilterNode,
    FrameAnalysis,
    FrameSampleReason,
    Glossary,
    GlossaryEntry,
    HighlightCandidate,
    HighlightFeatures,
    HighlightLabel,
    HighlightReason,
    HighlightSet,
    LipSyncEligibilityCriteria,
    LipSyncIneligibleReason,
    LipSyncMethod,
    LipSyncMode,
    LipSyncPlan,
    LipSyncQAReport,
    LipSyncReviewReason,
    LipSyncSegmentDecision,
    LocalizationQACheck,
    LocalizationQAFinding,
    LocalizationQAReport,
    LocalizationReview,
    LocalizationVariant,
    LocalizedSentence,
    LoudnessTarget,
    MediaProbe,
    PlatformPublishSpec,
    PreflightCheck,
    PreflightFinding,
    PreflightReport,
    ProblemDetail,
    ProducedBy,
    Project,
    PronunciationEntry,
    PronunciationLexicon,
    ProviderDescriptor,
    ProviderHealth,
    PublishAttempt,
    PublishConnectorCapability,
    PublishJob,
    PublishMethod,
    PublishPlatform,
    PublishState,
    QAFinding,
    QAFindingKind,
    QAReport,
    QASeverity,
    RationalTime,
    RationalTimeRange,
    ReeditPlan,
    ReframeFollow,
    ReframeHint,
    RemotionComposition,
    RemotionProp,
    RemotionRenderManifest,
    RemotionRenderRequest,
    RenderInput,
    RenderManifest,
    RenderStage,
    RenderTargetKind,
    ResolvedAsset,
    ResourceLimits,
    ReviewDecision,
    ReviewDecisionKind,
    ReviewPolicy,
    ReviewPolicyMode,
    ReviewScope,
    ReviewSeverity,
    ReviewState,
    RhetoricalBeat,
    RhetoricalBeatKind,
    SafeAreaSpec,
    ScriptSentence,
    ScriptVersion,
    Segment,
    SentenceReviewDecision,
    StorageRef,
    SubtitleCue,
    SubtitleLine,
    SubtitleStyleHint,
    SubtitleTemplate,
    SubtitleTrack,
    SubtitleWord,
    TaskEnvelope,
    TemplateTrustCriteria,
    TemplateTrustLevel,
    TemplateTrustState,
    TemplateTrustStats,
    TextLocalizationPlan,
    TextLocalizationStrategy,
    TextObservation,
    TextTrack,
    TextTrackKind,
    TextTrackLocalizationDecision,
    TextTrackSet,
    Track,
    TrackKind,
    Transcript,
    TranscriptModels,
    TranscriptSegment,
    TranscriptWord,
    TranslateReflectAdaptResult,
    TrendCluster,
    TrendItemSnapshot,
    TrendStage,
    TrendSubScores,
    TTSManifest,
    TTSProviderTier,
    TTSWordTiming,
    VideoBlueprint,
    VisualAnalysis,
    VisualBeat,
    VisualBeatKind,
    VisualMix,
    VoiceKind,
    VoiceLicenseStatus,
    VoiceProfile,
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


def make_video_blueprint() -> VideoBlueprint:
    return VideoBlueprint(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZB",
        source_artifact_id="01J2ZK3AC9V6XW8YQ4R5T6U7W1",
        duration_ms=58200,
        claims=[
            Claim(
                id="claim-0",
                text="这款芯片端侧推理速度是上代的两倍",
                entities=["M5"],
                source_status=ClaimSourceStatus.UNVERIFIED,
                evidence=[
                    EvidenceSpan(kind="transcript", ref_id="seg-0", start_ms=1400, end_ms=2480),
                    EvidenceSpan(kind="ocr", ref_id="tt-0", start_ms=1200, end_ms=3600),
                ],
            )
        ],
        rhetorical_beats=[
            RhetoricalBeat(
                id="rb-0", kind=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=2600,
                summary="开场抛出芯片话题",
            ),
            RhetoricalBeat(
                id="rb-1", kind=RhetoricalBeatKind.EVIDENCE, start_ms=2600, end_ms=40000,
                summary="跑分演示", claim_ids=["claim-0"],
            ),
            RhetoricalBeat(
                id="rb-2", kind=RhetoricalBeatKind.CTA, start_ms=40000, end_ms=58200,
                summary="关注引导",
            ),
        ],
        visual_beats=[
            VisualBeat(
                id="vb-0", kind=VisualBeatKind.PERSON, start_ms=0, end_ms=3000, frame_time_ms=0
            ),
            VisualBeat(
                id="vb-1", kind=VisualBeatKind.SCREEN_RECORD, start_ms=3000, end_ms=40000,
                frame_time_ms=3000,
            ),
        ],
        coverage=1.0,
        fusion_provider="llm.blueprint_fusion",
        created_at=_T0,
    )


def make_creative_opportunity() -> CreativeOpportunity:
    return CreativeOpportunity(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZC",
        trend_cluster_id="01J2ZK3AC9V6XW8YQ4R5T6U7X2",
        blueprint_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZB",
        source_asset_ids=["01J2ZK3AC9V6XW8YQ4R5T6U7W1"],
        vertical="ai-tech",
        rationale="跨平台热度上升且现有内容缺少实测成本角度",
        target_platform="douyin",
        target_language="zh-CN",
        created_at=_T0,
    )


def make_creative_brief() -> CreativeBrief:
    return CreativeBrief(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZD",
        opportunity_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZC",
        blueprint_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZB",
        claim_table_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZE",
        objective="45 秒讲清这款 AI 芯片更新对普通用户的真实影响",
        audience="中文 AI 工具用户",
        platform="douyin",
        target_language="zh-CN",
        duration_target_ms=45000,
        creation_mode=CreationMode.STRUCTURE_REWRITE,
        angle="实测成本与局限",
        hook=BriefHook(type="counter_intuitive_claim", promise="一个参数表没说的限制"),
        must_cover_claim_ids=["claim-0"],
        avoid=["照抄原标题", "未经证实的性能结论"],
        visual_mix=VisualMix(talking_head=0.25, screen_demo=0.35, broll=0.2, info_card=0.2),
        cta="评论区说你最想测试的场景",
        created_at=_T0,
    )


def make_claim_table() -> ClaimTable:
    return ClaimTable(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZE",
        source_blueprint_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZB",
        entries=[
            ClaimTableEntry(
                claim_id="claim-0",
                text="这款芯片端侧推理速度是上代的两倍",
                fact_status=ClaimSourceStatus.UNVERIFIED,
                evidence=[
                    EvidenceSpan(kind="transcript", ref_id="seg-0", start_ms=1400, end_ms=2480)
                ],
                confidence=0.6,
                recency="as_of_2026-07",
                allowed_phrasings=["官方称速度约为上代两倍（未独立验证）"],
                usable_in_rewrite=True,
            )
        ],
        created_at=_T0,
    )


def make_beat_template() -> BeatTemplate:
    return BeatTemplate(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZF",
        source_blueprint_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZB",
        duration_target_ms=45000,
        slots=[
            BeatSlot(id="slot-0", role=RhetoricalBeatKind.HOOK, start_ms=0, end_ms=3000,
                     target_duration_ms=3000, guidance="抛出反常识结论"),
            BeatSlot(id="slot-1", role=RhetoricalBeatKind.EVIDENCE, start_ms=3000, end_ms=40000,
                     target_duration_ms=37000, guidance="实测演示与数据"),
            BeatSlot(id="slot-2", role=RhetoricalBeatKind.CTA, start_ms=40000, end_ms=45000,
                     target_duration_ms=5000, guidance="引导互动"),
        ],
        created_at=_T0,
    )


def make_script_version() -> ScriptVersion:
    return ScriptVersion(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZG",
        brief_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZD",
        beat_template_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZF",
        claim_table_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZE",
        version=1,
        language="zh-CN",
        sentences=[
            ScriptSentence(
                id="s-0", beat_slot_id="slot-0", role=RhetoricalBeatKind.HOOK,
                text="有个参数表没告诉你的限制", target_duration_ms=2000, language="zh-CN",
            ),
            ScriptSentence(
                id="s-1", beat_slot_id="slot-1", role=RhetoricalBeatKind.EVIDENCE,
                text="官方称端侧推理约为上代两倍，我们实测记录如下",
                target_duration_ms=36000, claim_ids=["claim-0"], language="zh-CN",
            ),
            ScriptSentence(
                id="s-2", beat_slot_id="slot-2", role=RhetoricalBeatKind.CTA,
                text="评论区说你最想测的场景", target_duration_ms=2200, language="zh-CN",
            ),
        ],
        total_duration_ms=40200,
        rewrite_provider="llm.rewrite",
        created_at=_T0,
    )


def make_highlight_set() -> HighlightSet:
    features = HighlightFeatures(
        hook_strength=0.82, self_containedness=0.7, information_density=0.66,
        surprise_or_conflict=0.55, emotional_energy=0.5, topic_relevance=0.75,
        visual_activity=0.4, speaker_prominence=0.6, ending_payoff=0.72,
        context_dependency=0.2, technical_defect=0.05,
    )
    return HighlightSet(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZH",
        source_transcript_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZC",
        candidates=[
            HighlightCandidate(
                id="hl-0", source_transcript_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZC",
                start_ms=0, end_ms=18000, segment_ids=["seg-0", "seg-1", "seg-2"],
                score=0.5423, features=features,
                reason_codes=[HighlightReason.HOOK_QUOTE, HighlightReason.CLEAR_PAYOFF],
                human_label=HighlightLabel.SELECTED, human_label_reason="开场强、结尾有回报",
                weights_version="highlight-v1",
            ),
        ],
        weights_version="highlight-v1",
        feature_provider="highlight.fake",
        created_at=_T0,
    )


def make_canonical_script() -> CanonicalScript:
    return CanonicalScript(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZLC",
        script_version_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZG",
        source_language="zh-CN",
        sentences=[
            CanonicalSentence(
                id="cs-0", beat_slot_id="slot-0", role=RhetoricalBeatKind.HOOK,
                speaker_id="host", source_language="zh-CN",
                source_text="这款端侧模型能在 2GB 内存里跑起来",
                semantic_intent="强调关键性能钩子：小内存也能跑",
                claim_ids=["c-hook-0"],
                source_time_range_start_ms=0, source_time_range_end_ms=3000,
                target_duration_ms=3000,
                must_keep_terms=["2GB"], edit_flexibility=0.15,
            ),
            CanonicalSentence(
                id="cs-1", beat_slot_id="slot-1", role=RhetoricalBeatKind.EVIDENCE,
                source_language="zh-CN",
                source_text="实测推理时延 20ms，比上一代降低四成",
                semantic_intent="证据：延时与降幅",
                claim_ids=["c-evidence-0"],
                source_time_range_start_ms=3000, source_time_range_end_ms=8000,
                target_duration_ms=5000,
                must_keep_terms=["20ms"], edit_flexibility=0.1,
            ),
        ],
        total_duration_ms=8000,
        created_at=_T0,
    )


def make_glossary() -> Glossary:
    return Glossary(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZLG",
        source_language="zh-CN", target_language="en-US",
        entries=[
            GlossaryEntry(source_term="2GB", target_term="2 GB",
                            preserve_source=False, notes="英文加空格"),
            GlossaryEntry(source_term="端侧", target_term="on-device"),
            GlossaryEntry(source_term="20ms", target_term="20 ms",
                            preserve_source=False),
            GlossaryEntry(source_term="Qwen", target_term="Qwen",
                            preserve_source=True, pronunciation="/tʃwɛn/",
                            notes="产品名不译"),
        ],
        version=1, created_at=_T0,
    )


def make_translate_reflect_adapt_result() -> TranslateReflectAdaptResult:
    return TranslateReflectAdaptResult(
        canonical_sentence_id="cs-1",
        target_language="en-US",
        draft_text="Measured inference latency is 20 milliseconds, 40% lower than last gen.",
        reflected_notes=["数值单位符合术语表", "'lower than' 语义与源一致"],
        adapted_text="Inference clocks in at 20 ms — 40% lower than last gen.",
        alternatives=["Inference now runs at 20 ms, a 40% drop from last gen."],
        semantic_similarity=0.94,
        duration_estimate_ms=5000,
        claim_diff=ClaimDiff(
            source_claim_ids=["c-evidence-0"],
            localized_claim_ids=["c-evidence-0"],
            deltas=[],
        ),
        provider="tra.fake",
    )


def make_localization_variant() -> LocalizationVariant:
    return LocalizationVariant(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZLV",
        canonical_script_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZLC",
        target_language="en-US",
        glossary_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZLG",
        sentences=[
            LocalizedSentence(
                id="ls-0", canonical_sentence_id="cs-0", target_language="en-US",
                text="This on-device model runs in just 2 GB of RAM.",
                claim_ids=["c-hook-0"],
                claim_source_status=ClaimSourceStatus.VERIFIED,
                duration_estimate_ms=3200, semantic_similarity=0.92,
                needs_review=False, review_reasons=[],
            ),
            LocalizedSentence(
                id="ls-1", canonical_sentence_id="cs-1", target_language="en-US",
                text="Inference clocks in at 20 ms — 40% lower than last gen.",
                claim_ids=["c-evidence-0"],
                claim_source_status=ClaimSourceStatus.VERIFIED,
                duration_estimate_ms=5000, semantic_similarity=0.94,
                needs_review=False,
            ),
        ],
        provider="tra.fake",
        total_duration_estimate_ms=8200,
        created_at=_T0,
    )


def make_subtitle_template() -> SubtitleTemplate:
    return SubtitleTemplate(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7SUB1",
        language="zh-CN",
        max_chars_per_line=16,
        max_lines_per_cue=2,
        cjk_chars_per_sec=8.0,
        min_cue_duration_ms=800,
        max_cue_duration_ms=6000,
        safe_area=SafeAreaSpec(
            left_min_pct=5.0, right_max_pct=95.0,
            top_min_pct=5.0, bottom_max_pct=90.0,
        ),
        style_hint=SubtitleStyleHint(
            font_family="Source Han Sans", font_size_pt=48, bold=True,
            color="#FFFFFF", outline_color="#000000", outline_width=2.0,
        ),
        version=1, created_at=_T0,
    )


def make_subtitle_track() -> SubtitleTrack:
    return SubtitleTrack(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7SUB2",
        language="zh-CN",
        template_id="01J2ZK3AC9V6XW8YQ4R5T6U7SUB1",
        source_transcript_id="01J2ZK3AC9V6XW8YQ4R5T6U7Y0",
        alignment_provider="asr.fake",
        cues=[
            SubtitleCue(
                id="cue-0", start_ms=120, end_ms=2480,
                lines=[SubtitleLine(
                    text="今天带大家拆解这款 AI 芯片",
                    start_ms=120, end_ms=2480, language="zh-CN",
                    words=[
                        SubtitleWord(text="今天", start_ms=120, end_ms=520,
                                        confidence=0.95),
                        SubtitleWord(text="AI", start_ms=1400, end_ms=1720,
                                        confidence=0.55),
                        SubtitleWord(text="芯片", start_ms=1720, end_ms=2480,
                                        confidence=0.9),
                    ],
                )],
                source_ref_kind="transcript_segment", source_ref_id="seg-0",
            ),
            SubtitleCue(
                id="cue-1", start_ms=2600, end_ms=5000,
                lines=[SubtitleLine(
                    text="端侧推理只用了 20 毫秒",
                    start_ms=2600, end_ms=5000, language="zh-CN",
                )],
                source_ref_kind="transcript_segment", source_ref_id="seg-1",
            ),
        ],
        created_at=_T0,
    )


def make_text_localization_plan() -> TextLocalizationPlan:
    return TextLocalizationPlan(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7OTX1",
        source_text_track_set_id="01J2ZK3AC9V6XW8YQ4R5T6U7Y5",
        policy_id="01J2ZK3AC9V6XW8YQ4R5T6U7OTX0",
        target_language="en-US",
        decisions=[
            TextTrackLocalizationDecision(
                source_track_id="tt-caption-0",
                source_text="端侧推理 20ms 完成",
                source_kind=TextTrackKind.CAPTION,
                target_language="en-US",
                strategy=TextLocalizationStrategy.REDRAW,
                translated_text="On-device inference in 20 ms",
                clean_plate_request_id="cp-0",
                layout_expansion_ratio=1.15,
                rationale="CAPTION 默认重绘，遮挡低且授权无限制",
            ),
            TextTrackLocalizationDecision(
                source_track_id="tt-brand-1",
                source_text="Qwen Logo",
                source_kind=TextTrackKind.BRAND_MARK,
                target_language="en-US",
                strategy=TextLocalizationStrategy.SKIP,
                translated_text=None,
                needs_review=True,
                rationale="BRAND_MARK 未授权，交人工确认（§6.1 红线）",
            ),
            TextTrackLocalizationDecision(
                source_track_id="tt-scene-2",
                source_text="Coffee",
                source_kind=TextTrackKind.SCENE_TEXT,
                target_language="en-US",
                strategy=TextLocalizationStrategy.KEEP_AS_IS,
                translated_text=None,
                rationale="SCENE_TEXT 不重要，默认保留",
            ),
        ],
        clean_plate_requests=[
            CleanPlateRequest(
                id="cp-0", source_track_id="tt-caption-0",
                source_artifact_id="01J2ZK3AC9V6XW8YQ4R5T6U7W1",
                frame_start_ms=120, frame_end_ms=2480,
                method=CleanPlateMethod.BACKGROUND_ESTIMATE,
            ),
        ],
        created_at=_T0,
        provider="onscreen_text.fake",
    )


def make_voice_profile() -> VoiceProfile:
    return VoiceProfile(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7TTS1",
        display_name="Anchor A（Cloud HQ）",
        language="zh-CN",
        voice_kind=VoiceKind.CLONED,
        license_status=VoiceLicenseStatus.AUTHORIZED,
        provider_tier=TTSProviderTier.CLOUD_HIGH_QUALITY,
        provider_voice_id="azure-neural-female-1",
        sample_source_ref="artifact://sample/anchor-a-consent-2026.wav",
        consent_ref="consent://anchor-a-2026-signed",
        notes="Anchor A cloned voice; 6-month license",
        created_at=_T0,
    )


def make_pronunciation_lexicon() -> PronunciationLexicon:
    return PronunciationLexicon(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7TTS2",
        language="en-US",
        provider_tier=TTSProviderTier.CLOUD_HIGH_QUALITY,
        entries=[
            PronunciationEntry(surface="Qwen", pronunciation="/tʃwɛn/",
                                  notes="product name"),
            PronunciationEntry(surface="LoRA", pronunciation="/ˈloʊ.rə/"),
        ],
        version=1, created_at=_T0,
    )


def make_tts_manifest() -> TTSManifest:
    return TTSManifest(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7TTS3",
        sentence_id="ls-0",
        voice_profile_id="01J2ZK3AC9V6XW8YQ4R5T6U7TTS1",
        language="en-US",
        text_hash="a" * 64,
        provider="tts.cloud.fake",
        provider_tier=TTSProviderTier.CLOUD_HIGH_QUALITY,
        tool_version="fake-tts-1.0",
        audio_artifact_id="artifact://tts/ls-0.wav",
        duration_ms=3200,
        word_timings=[
            TTSWordTiming(text="This", start_ms=0, end_ms=280, confidence=0.98),
            TTSWordTiming(text="on-device", start_ms=280, end_ms=1200,
                             confidence=0.97),
            TTSWordTiming(text="model", start_ms=1200, end_ms=1720,
                             confidence=0.97),
        ],
        speed_used=1.0,
        seed=42,
        created_at=_T0,
    )


def make_duration_fit_plan() -> DurationFitPlan:
    return DurationFitPlan(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7DF01",
        localization_variant_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZLV",
        decisions=[
            DurationFitDecision(
                sentence_id="ls-0", estimated_ms=3200, target_ms=3000,
                fit_method=DurationFitStrategy.TTS_SPEED,
                final_ratio=1.067,
                status=DurationFitStatus.OK_FITTED,
                rationale="TTS 语速 1.07x 在自然区间 [0.92, 1.08]，命中",
            ),
            DurationFitDecision(
                sentence_id="ls-1", estimated_ms=5000, target_ms=5000,
                final_ratio=1.0,
                status=DurationFitStatus.OK_UNCHANGED,
                rationale="估算已等于预算，无需拟合",
            ),
        ],
        created_at=_T0,
    )


def make_audio_mix_plan() -> AudioMixPlan:
    return AudioMixPlan(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7AM01",
        tracks=[
            AudioMixTrack(
                id="voice-dub", kind=AudioMixTrackKind.VOICE_DUB,
                tts_manifest_id="01J2ZK3AC9V6XW8YQ4R5T6U7TTS3",
                start_ms=0, end_ms=8200, gain_db=0.0,
            ),
            AudioMixTrack(
                id="music", kind=AudioMixTrackKind.MUSIC,
                source_artifact_id="artifact://music/bg.mp3",
                start_ms=0, end_ms=8200, gain_db=-6.0,
                ducked_by="voice-dub",
            ),
        ],
        ducking=DuckingPolicy(
            sidechain=DuckingSidechain.VOICE_ACTIVITY,
            threshold_db=-20.0, ratio=8.0,
            attack_ms=20, release_ms=300, reduction_db=-8.0,
        ),
        loudness_target=LoudnessTarget(
            lufs=-14.0, lufs_tolerance=2.0, true_peak_max_dbtp=-1.0,
        ),
        room_tone_artifact_id="artifact://ambience/room.wav",
        total_duration_ms=8200,
        created_at=_T0,
    )


def make_lipsync_plan() -> LipSyncPlan:
    return LipSyncPlan(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7LS01",
        localization_variant_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZLV",
        mode=LipSyncMode.AUTO_ELIGIBLE,
        criteria=LipSyncEligibilityCriteria(),
        decisions=[
            LipSyncSegmentDecision(
                segment_id="ls-0", start_ms=0, end_ms=3000,
                eligible=True,
                method=LipSyncMethod.GPU_SYNTHESIS,
                synthesized_artifact_id="artifact://lipsync/ls-0.mp4",
                qa=LipSyncQAReport(
                    boundary_score=0.92, skin_tone_score=0.9,
                    motion_score=0.88, identity_score=0.95, passed=True,
                ),
                rationale="单主脸、遮挡小、配音已对齐 → GPU 合成，QA 通过",
            ),
            LipSyncSegmentDecision(
                segment_id="ls-1", start_ms=3000, end_ms=6000,
                eligible=False,
                ineligible_reasons=[LipSyncIneligibleReason.MULTIPLE_FACES],
                method=LipSyncMethod.BROLL_COVER,
                needs_review=True,
                review_reasons=[LipSyncReviewReason.FALLBACK_USED],
                rationale="多脸不合格 → 无相近原 Take，插 B-roll 覆盖",
            ),
        ],
        created_at=_T0,
    )


def make_localization_qa_report() -> LocalizationQAReport:
    return LocalizationQAReport(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7LQ01",
        localization_variant_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZLV",
        findings=[
            LocalizationQAFinding(
                sentence_id="ls-0", check=LocalizationQACheck.SUBTITLE_READING_SPEED,
                severity=QASeverity.MINOR,
                detail="英文 CPS 略高，建议缩短或延长该 cue",
            ),
        ],
        reviewed_sentence_ids=["ls-0", "ls-1"],
        pass_or_block=True,  # 仅 MINOR，无 BLOCKER
        created_at=_T0,
    )


def make_localization_review() -> LocalizationReview:
    return LocalizationReview(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7LR01",
        localization_variant_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZLV",
        decisions=[
            SentenceReviewDecision(
                sentence_id="ls-0", state=ReviewState.APPROVED, reviewer="editor-a",
            ),
            SentenceReviewDecision(
                sentence_id="ls-1", state=ReviewState.EDITED, reviewer="editor-a",
                edited_text="端侧 AI 芯片把推理带到本地。",
                note="更贴近平台口语",
            ),
        ],
        created_at=_T0,
    )


def make_review_decision() -> ReviewDecision:
    return ReviewDecision(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7RD01",
        decision=ReviewDecisionKind.APPROVED,
        scope=ReviewScope.VARIANT,
        entity_id="var_123",
        entity_version=7,
        content_digest="c" * 64,
        reviewer_id="usr_1",
        policy_snapshot_id="pol_2",
        qc_report_ids=["qc_9"],
        signature="deadbeef" * 8,
        created_at=_T0,
    )


def make_review_policy() -> ReviewPolicy:
    return ReviewPolicy(
        id="pol_2",
        mode=ReviewPolicyMode.NEW_TEMPLATE_ONLY,
        warning_blocks=False,
        version=1,
        created_at=_T0,
    )


def make_template_trust_state() -> TemplateTrustState:
    return TemplateTrustState(
        template_id="tpl_ai_zh_en",
        template_version=3,
        level=TemplateTrustLevel.TRUSTED,
        stats=TemplateTrustStats(
            approved_render_count=24,
            recent_fatal_count=0,
            recent_error_rate=0.02,
            qa_meets_standard=True,
            publish_success_ok=True,
            duplicate_publish_ok=True,
            owner_approved=True,
        ),
        criteria=TemplateTrustCriteria(),
        updated_at=_T0,
    )


def make_platform_publish_spec() -> PlatformPublishSpec:
    return PlatformPublishSpec(
        platform=PublishPlatform.TIKTOK,
        allowed_aspect_ratios=["9:16"],
        min_width=360, min_height=640, max_width=1080, max_height=1920,
        allowed_video_codecs=["h264", "h265"],
        allowed_audio_codecs=["aac"],
        allowed_containers=["mp4", "mov"],
        max_file_size_bytes=500_000_000,
        min_duration_ms=3000, max_duration_ms=600_000,
        title_max_len=150, description_max_len=2200,
        max_tags=20, tag_max_len=100,
        banned_title_chars=["<", ">"],
    )


def make_publish_connector_capability() -> PublishConnectorCapability:
    return PublishConnectorCapability(
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.OFFICIAL_API,
        available=True,
        direct_post=True,
        auth_status=AuthStatus.AUTHORIZED,
        client_review_status=ClientReviewStatus.APPROVED,
        account_status=AccountStatus.ACTIVE,
        supported_containers=["mp4", "mov"],
        max_file_size_bytes=500_000_000,
    )


def make_preflight_report() -> PreflightReport:
    return PreflightReport(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7PF01",
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.OFFICIAL_API,
        findings=[
            PreflightFinding(
                check=PreflightCheck.REVIEW_STATUS,
                severity=ReviewSeverity.INFO,
                detail="客户端已审核，无可见性限制",
            ),
        ],
        publishable=True,
        created_at=_T0,
    )


def make_publish_job() -> PublishJob:
    return PublishJob(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7PJ01",
        idempotency_key="e3b0c44298fc1c149afbf4c8996fb924" * 2,
        account_id="acct_tt_9",
        platform=PublishPlatform.TIKTOK,
        method=PublishMethod.OFFICIAL_API,
        render_digest="r" * 64,
        metadata_digest="m" * 64,
        scheduled_window="immediate",
        state=PublishState.SUCCEEDED,
        external_post_id="tt_post_7788",
        external_url="https://www.tiktok.com/@acct/video/7788",
        content_fingerprint="cf_abc",
        attempts=[
            PublishAttempt(
                attempt=1, request_digest="req_1",
                external_upload_token="up_1", external_post_token="post_1",
                at=_T0,
            ),
        ],
        created_at=_T0,
        updated_at=_T0,
    )


def make_reedit_plan() -> ReeditPlan:
    return ReeditPlan(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZK",
        source_transcript_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZC",
        source_asset_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZA",
        ops=[
            EditOp(
                id="op-0", op=EditOpKind.KEEP, source_start_ms=0, source_end_ms=5000,
                segment_ids=["seg-0"], output_order=0,
                reframe=ReframeHint(target_aspect_ratio="9:16", follow=ReframeFollow.SPEAKER),
            ),
            EditOp(
                id="op-1", op=EditOpKind.DELETE, source_start_ms=5000, source_end_ms=6200,
                segment_ids=["seg-1"], reason="filler",
            ),
            EditOp(
                id="op-2", op=EditOpKind.KEEP, source_start_ms=6200, source_end_ms=12000,
                segment_ids=["seg-2"], output_order=1,
                reframe=ReframeHint(target_aspect_ratio="9:16", follow=ReframeFollow.SPEAKER),
            ),
        ],
        continuity=[
            ContinuityNote(kind=ContinuityRuleKind.JUMPCUT_SMOOTH, at_ms=5000,
                           detail="删除填充段后 seg-0→seg-2 相邻，用推拉平滑"),
        ],
        kept_duration_ms=10800,
        created_at=_T0,
    )


def make_asset_plan() -> AssetPlan:
    slot = AssetPlanSlot(
        slot_id="slot-0",
        start_ms=0,
        end_ms=5000,
        role=AssetRole.SCREEN_DEMO,
        query="macOS local inference settings panel",
        semantic_requirements=["must show settings panel"],
        composition=CompositionSpec(aspect_ratio="9:16", safe_area="center"),
        allowed_sources=[AssetSource.SOURCE, AssetSource.OWN_LIBRARY, AssetSource.STOCK],
        fallback=AssetRole.INFO_CARD,
    )
    resolved = ResolvedAsset(
        slot_id="slot-0",
        asset_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZM",
        source=AssetSource.OWN_LIBRARY,
        license=AssetLicense(type=AssetLicenseType.OWNED, holder="videoforge"),
        query="macOS local inference settings panel",
        usage_start_ms=0,
        usage_end_ms=5000,
        match_score=0.82,
        provider="own_library.fake",
    )
    return AssetPlan(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZL",
        source_transcript_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZC",
        slots=[slot],
        resolved=[resolved],
        weights_version="asset-v1",
        created_at=_T0,
    )


def make_creative_timeline() -> CreativeTimeline:
    rate = 30  # 30 fps 基准
    def rt(v: int) -> RationalTime:
        return RationalTime(value=v, rate=rate)

    v1 = Track(
        id="v1", kind=TrackKind.V1_PRIMARY_VIDEO,
        segments=[
            Segment(
                id="v1-s0",
                time_range=RationalTimeRange(start=rt(0), duration=rt(150)),  # 5 秒
                source_ref="01J2ZK3AC9V6XW8YQ4R5T6U7ZA", semantic_role="HOOK",
                script_sentence_id="s-0", speaker_id="host",
                provenance_ref="01J2ZK3AC9V6XW8YQ4R5T6U7ZM",  # ResolvedAsset id
                template_slot="slot-0",
            ),
        ],
    )
    v4 = Track(
        id="v4", kind=TrackKind.V4_CAPTIONS,
        segments=[
            Segment(id="v4-s0",
                    time_range=RationalTimeRange(start=rt(0), duration=rt(150)),
                    script_sentence_id="s-0"),
        ],
    )
    a0 = Track(
        id="a0", kind=TrackKind.A0_ORIGINAL,
        segments=[
            Segment(id="a0-s0",
                    time_range=RationalTimeRange(start=rt(0), duration=rt(150)),
                    source_ref="01J2ZK3AC9V6XW8YQ4R5T6U7ZA"),
        ],
    )
    return CreativeTimeline(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZN",
        project_id="01J2ZK3AC9V6XW8YQ4R5T6U7Z0",
        rate=rate,
        duration=rt(150),
        tracks=[v1, v4, a0],
        source_transcript_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZC",
        source_asset_ids=["01J2ZK3AC9V6XW8YQ4R5T6U7ZA"],
        created_at=_T0,
    )


def make_render_manifest() -> RenderManifest:
    # 结构化 FilterGraph 供 domain 编译器序列化为 -filter_complex；args 只含纯 argv 参数，
    # 绝无 shell 拼接、绝无 filter_complex 长串（分号是 ffmpeg 分隔符，会误触本层拒绝）。
    render_graph = FfmpegRenderGraph(
        args=[
            "ffmpeg", "-y", "-hide_banner",
            "-i", "/staging/source.mp4",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "/output/final.mp4",
        ],
        filter_complex=FilterGraph(
            nodes=[
                FilterNode(id="n0", filter="scale", params={"w": "1080", "h": "1920"},
                           inputs=["0:v"], outputs=["v_scaled"]),
                FilterNode(id="n1", filter="setsar", params={"sar": "1"},
                           inputs=["v_scaled"], outputs=["v"]),
                FilterNode(id="n2", filter="aformat", params={"sample_fmts": "fltp"},
                           inputs=["0:a"], outputs=["a"]),
            ],
            sinks=["v", "a"],
        ),
        inputs=[RenderInput(asset_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZA",
                             sha256="a" * 64, resolved_path="/staging/source.mp4",
                             role="video")],
        output_path="/output/final.mp4",
        target=RenderTargetKind.MP4_H264,
        tool_version="ffmpeg-8.1.2",
    )
    return RenderManifest(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZP",
        timeline_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZN",
        stage=RenderStage.FINAL,
        render_graph=render_graph,
        input_digests={"01J2ZK3AC9V6XW8YQ4R5T6U7ZA": "a" * 64},
        output_digest="b" * 64,
        duration_ms=45000,
        tool_version="ffmpeg-8.1.2",
        created_at=_T0,
    )


def make_remotion_render_manifest() -> RemotionRenderManifest:
    request = RemotionRenderRequest(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZQ",
        timeline_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZN",
        composition=RemotionComposition.CAPTIONS,
        props=[
            RemotionProp(key="segments", value=[
                {"text": "大家好", "start_ms": 0, "end_ms": 1500},
                {"text": "今天带大家拆解", "start_ms": 1500, "end_ms": 4500},
            ]),
            RemotionProp(key="font_family", value="Noto Sans CJK SC"),
            RemotionProp(key="font_size_px", value=48),
            RemotionProp(key="show_background", value=True),
        ],
        duration_ms=45000,
        fps=30,
        width=1080,
        height=1920,
        entry_component_path="/staging/remotion/Root.tsx",
        output_path="/output/captions.mp4",
        tool_version="remotion-4.0.240",
    )
    return RemotionRenderManifest(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZR",
        request=request,
        input_digests={"01J2ZK3AC9V6XW8YQ4R5T6U7ZA": "a" * 64},
        output_digest="c" * 64,
        tool_version="remotion-4.0.240",
        created_at=_T0,
    )


def make_qa_report() -> QAReport:
    return QAReport(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZS",
        timeline_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZN",
        render_manifest_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZP",
        findings=[
            QAFinding(
                id="f-0", kind=QAFindingKind.CAPTION_OFF_SAFE_AREA, severity=QASeverity.MINOR,
                at_ms=12000, duration_ms=800, track_ref="v4",
                detail="字幕底部越出 90% 安全区",
                evidence={"y_bottom_pct": 96.2, "safe_area_bottom_pct": 90.0},
            ),
            QAFinding(
                id="f-1", kind=QAFindingKind.LOUDNESS_OUT_OF_RANGE, severity=QASeverity.MAJOR,
                at_ms=0, duration_ms=45000, track_ref="a2",
                detail="整体响度 -20 LUFS 低于目标 -14 ±2",
                evidence={"lufs": -20.1, "target_min": -16.0, "target_max": -12.0},
            ),
        ],
        timeline_duration_ms=45000,
        measured_duration_ms=45000,
        pass_or_block=True,
        created_at=_T0,
    )


def make_exporter_report() -> ExporterReport:
    return ExporterReport(
        id="01J2ZK3AC9V6XW8YQ4R5T6U7ZT",
        timeline_id="01J2ZK3AC9V6XW8YQ4R5T6U7ZN",
        entries=[
            ExportEntry(kind=ExporterKind.OTIO_FILE, status=ExporterStatus.OK,
                         output_path="/output/timeline.otio",
                         tool_version="videoforge.otio.writer@0.1.0",
                         bytes_written=2048),
            ExportEntry(kind=ExporterKind.FCPXML, status=ExporterStatus.OK,
                         output_path="/output/timeline.fcpxml",
                         tool_version="videoforge.fcpxml.writer@0.1.0",
                         bytes_written=4096),
            ExportEntry(kind=ExporterKind.JIANYING, status=ExporterStatus.PARTIAL,
                         output_path="/output/jianying-package/",
                         tool_version="videoforge.jianying.writer@0.1.0-experimental",
                         warnings=["新版本 Draft 加密；已产出包+README 说明供人工导入"]),
            ExportEntry(kind=ExporterKind.CAPCUT, status=ExporterStatus.UNSUPPORTED,
                         tool_version="videoforge.capcut.writer@0.1.0-experimental",
                         errors=["CapCut Draft Adapter 尚未支持该模板"]),
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
    "video-blueprint": make_video_blueprint(),
    "creative-opportunity": make_creative_opportunity(),
    "creative-brief": make_creative_brief(),
    "claim-table": make_claim_table(),
    "beat-template": make_beat_template(),
    "script-version": make_script_version(),
    "highlight-set": make_highlight_set(),
    "canonical-script": make_canonical_script(),
    "glossary": make_glossary(),
    "translate-reflect-adapt-result": make_translate_reflect_adapt_result(),
    "localization-variant": make_localization_variant(),
    "subtitle-template": make_subtitle_template(),
    "subtitle-track": make_subtitle_track(),
    "text-localization-plan": make_text_localization_plan(),
    "voice-profile": make_voice_profile(),
    "pronunciation-lexicon": make_pronunciation_lexicon(),
    "tts-manifest": make_tts_manifest(),
    "duration-fit-plan": make_duration_fit_plan(),
    "audio-mix-plan": make_audio_mix_plan(),
    "lipsync-plan": make_lipsync_plan(),
    "localization-qa-report": make_localization_qa_report(),
    "localization-review": make_localization_review(),
    "review-decision": make_review_decision(),
    "review-policy": make_review_policy(),
    "template-trust-state": make_template_trust_state(),
    "platform-publish-spec": make_platform_publish_spec(),
    "publish-connector-capability": make_publish_connector_capability(),
    "preflight-report": make_preflight_report(),
    "publish-job": make_publish_job(),
    "reedit-plan": make_reedit_plan(),
    "asset-plan": make_asset_plan(),
    "creative-timeline": make_creative_timeline(),
    "render-manifest": make_render_manifest(),
    "remotion-render-manifest": make_remotion_render_manifest(),
    "qa-report": make_qa_report(),
    "exporter-report": make_exporter_report(),
}
