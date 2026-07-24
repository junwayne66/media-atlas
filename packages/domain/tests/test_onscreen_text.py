"""VF-403 画面文字本地化决策 domain 测试。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    CleanPlateMethod,
    CleanPlateRequest,
    Glossary,
    GlossaryEntry,
    TextLocalizationKindPolicy,
    TextLocalizationPlan,
    TextLocalizationPolicy,
    TextLocalizationStrategy,
    TextObservation,
    TextTrack,
    TextTrackKind,
    TextTrackLocalizationDecision,
    TextTrackSet,
)
from videoforge_domain import (
    TextLocalizationIssueKind,
    decide_strategy,
    is_valid_text_localization_plan,
    plan_text_localization,
    validate_text_localization_plan,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _bbox(**k):
    from videoforge_contracts import BBox
    return BBox(x=k.get("x", 0.1), y=k.get("y", 0.85),
                 w=k.get("w", 0.6), h=k.get("h", 0.08))


def _track(
    tid: str = "tt-0", kind: TextTrackKind = TextTrackKind.CAPTION,
    text: str = "端侧推理 20ms 完成", confidence: float = 0.95,
    low_confidence: bool = False, occluded_frames: int = 0, obs_count: int = 4,
) -> TextTrack:
    observations = [
        TextObservation(
            frame_time_ms=i * 200, bbox=_bbox(),
            text=text, confidence=confidence,
            occluded=(i < occluded_frames),
        )
        for i in range(obs_count)
    ]
    return TextTrack(
        id=tid, source_artifact_id="art-0", kind=kind, text=text,
        start_ms=0, end_ms=obs_count * 200,
        confidence=confidence, low_confidence=low_confidence,
        observations=observations,
    )


def _policy(
    per_kind: list[TextLocalizationKindPolicy] | None = None,
    max_occlusion: float = 0.3, max_expansion: float = 1.3,
) -> TextLocalizationPolicy:
    # 注意：`per_kind is None` 才用默认；传空列表要保留空列表（Python 惯用陷阱）
    return TextLocalizationPolicy(
        id="pol", source_language="zh-CN", target_language="en-US",
        per_kind=(per_kind if per_kind is not None else [
            TextLocalizationKindPolicy(
                kind=TextTrackKind.CAPTION,
                default_strategy=TextLocalizationStrategy.REDRAW,
                min_confidence_for_auto=0.7,
                fallback_strategy=TextLocalizationStrategy.INFO_CARD_FALLBACK,
            ),
            TextLocalizationKindPolicy(
                kind=TextTrackKind.UI,
                default_strategy=TextLocalizationStrategy.LOCALIZE_ANNOTATION,
                requires_license_check=True,
                fallback_strategy=TextLocalizationStrategy.SKIP,
            ),
            TextLocalizationKindPolicy(
                kind=TextTrackKind.SCENE_TEXT,
                default_strategy=TextLocalizationStrategy.KEEP_AS_IS,
                fallback_strategy=TextLocalizationStrategy.KEEP_AS_IS,
            ),
        ]),
        max_occlusion_for_redraw=max_occlusion,
        max_layout_expansion_ratio=max_expansion,
        created_at=_T0,
    )


# —— decide_strategy 硬红线 ——

def test_brand_mark_always_skip_even_if_policy_says_redraw() -> None:
    """§6.1 硬红线：BRAND_MARK 无论 policy 怎么配置都不作为普通翻译。"""
    per = [TextLocalizationKindPolicy(
        kind=TextTrackKind.BRAND_MARK,
        default_strategy=TextLocalizationStrategy.REDRAW,  # 恶意策略
    )]
    d = decide_strategy(_track(kind=TextTrackKind.BRAND_MARK, text="Qwen"),
                          policy=_policy(per_kind=per),
                          translated_text="Qwen (translated)")
    assert d.strategy is TextLocalizationStrategy.SKIP
    assert d.translated_text is None
    assert d.needs_review


def test_unknown_kind_goes_to_skip_review() -> None:
    d = decide_strategy(_track(kind=TextTrackKind.UNKNOWN, text="???"),
                          policy=_policy())
    assert d.strategy is TextLocalizationStrategy.SKIP
    assert d.needs_review


def test_ui_requires_license_check_falls_to_annotation() -> None:
    d = decide_strategy(_track(kind=TextTrackKind.UI, text="Save"),
                          policy=_policy(),
                          translated_text="保存")
    assert d.strategy is TextLocalizationStrategy.LOCALIZE_ANNOTATION
    assert d.needs_review


def test_caption_high_confidence_low_occlusion_goes_redraw() -> None:
    d = decide_strategy(_track(), policy=_policy(),
                          translated_text="On-device 20 ms")
    assert d.strategy is TextLocalizationStrategy.REDRAW
    assert d.translated_text == "On-device 20 ms"
    assert not d.needs_review


def test_caption_low_confidence_falls_back_to_info_card() -> None:
    d = decide_strategy(_track(confidence=0.5, low_confidence=True),
                          policy=_policy(), translated_text="x")
    assert d.strategy is TextLocalizationStrategy.INFO_CARD_FALLBACK
    assert d.needs_review


def test_caption_high_occlusion_falls_back() -> None:
    # 4 frames, occluded_frames=2 → 0.5 > 0.3
    d = decide_strategy(_track(occluded_frames=2),
                          policy=_policy(max_occlusion=0.3),
                          translated_text="x")
    assert d.strategy is TextLocalizationStrategy.INFO_CARD_FALLBACK


def test_caption_layout_overflow_falls_back() -> None:
    d = decide_strategy(_track(), policy=_policy(max_expansion=1.3),
                          translated_text="x", layout_expansion_ratio=1.5)
    assert d.strategy is TextLocalizationStrategy.INFO_CARD_FALLBACK


def test_scene_text_default_keep() -> None:
    d = decide_strategy(_track(kind=TextTrackKind.SCENE_TEXT, text="Coffee"),
                          policy=_policy())
    assert d.strategy is TextLocalizationStrategy.KEEP_AS_IS
    assert d.translated_text is None  # KEEP_AS_IS 不带译文


def test_kind_without_policy_safe_default() -> None:
    p = _policy(per_kind=[])
    d = decide_strategy(_track(), policy=p)
    assert d.strategy is TextLocalizationStrategy.SKIP
    assert d.needs_review


# —— plan_text_localization ——

def test_plan_generates_clean_plate_only_for_redraw() -> None:
    tts = TextTrackSet(
        id="tts-0", tracks=[
            _track(tid="c-cap", kind=TextTrackKind.CAPTION),
            _track(tid="c-brand", kind=TextTrackKind.BRAND_MARK, text="Logo"),
            _track(tid="c-scene", kind=TextTrackKind.SCENE_TEXT, text="Coffee"),
        ],
        ocr_provider="fake", created_at=_T0,
    )
    p = plan_text_localization(
        tts, policy=_policy(), plan_id="pl-0", created_at=_T0,
        translations={"c-cap": "On-device 20 ms"},
    )
    assert len(p.decisions) == 3
    # 只有 CAPTION 走 REDRAW 且带 Clean Plate
    caption_d = next(d for d in p.decisions if d.source_track_id == "c-cap")
    assert caption_d.strategy is TextLocalizationStrategy.REDRAW
    assert caption_d.clean_plate_request_id is not None
    assert len(p.clean_plate_requests) == 1
    assert p.clean_plate_requests[0].method is CleanPlateMethod.BACKGROUND_ESTIMATE
    # BRAND_MARK / SCENE_TEXT 无 Clean Plate
    brand_d = next(d for d in p.decisions if d.source_track_id == "c-brand")
    scene_d = next(d for d in p.decisions if d.source_track_id == "c-scene")
    assert brand_d.clean_plate_request_id is None
    assert scene_d.clean_plate_request_id is None


# —— validate_text_localization_plan ——

def _clean_plan(decisions: list[TextTrackLocalizationDecision],
                  requests: list[CleanPlateRequest] | None = None,
                  ) -> TextLocalizationPlan:
    return TextLocalizationPlan(
        id="pl", source_text_track_set_id="tts", policy_id="pol",
        target_language="en-US", decisions=decisions,
        clean_plate_requests=requests or [],
        created_at=_T0,
    )


def _decision(**k):
    defaults = dict(
        source_track_id="tt-0", source_text="x", source_kind=TextTrackKind.CAPTION,
        target_language="en-US", strategy=TextLocalizationStrategy.REDRAW,
        translated_text="y", rationale="ok",
    )
    defaults.update(k)
    return TextTrackLocalizationDecision(**defaults)


def test_validate_empty_plan_fails() -> None:
    p = _clean_plan([])
    kinds = [i.kind for i in validate_text_localization_plan(p, policy=_policy())]
    assert TextLocalizationIssueKind.EMPTY_PLAN in kinds


def test_validate_brand_mark_illegal_strategy() -> None:
    """BRAND_MARK 若被手工构造成 REDRAW，validate 应拦。"""
    p = _clean_plan([_decision(
        source_track_id="brand-0", source_text="Qwen",
        source_kind=TextTrackKind.BRAND_MARK,
        strategy=TextLocalizationStrategy.REDRAW,
        translated_text="Qwen (en)",
        clean_plate_request_id="cp-0",
    )], requests=[CleanPlateRequest(
        id="cp-0", source_track_id="brand-0", source_artifact_id="art",
        frame_start_ms=0, frame_end_ms=100,
        method=CleanPlateMethod.BACKGROUND_ESTIMATE,
    )])
    kinds = [i.kind for i in validate_text_localization_plan(p, policy=_policy())]
    assert TextLocalizationIssueKind.BRAND_MARK_ILLEGAL_STRATEGY in kinds


def test_validate_unknown_kind_must_skip() -> None:
    p = _clean_plan([_decision(
        source_kind=TextTrackKind.UNKNOWN,
        strategy=TextLocalizationStrategy.KEEP_AS_IS,
        translated_text=None,
    )])
    # KIND_POLICY_MISSING（默认 policy 无 UNKNOWN）+ UNKNOWN_KIND_NOT_ROUTED 都可能有
    kinds = [i.kind for i in validate_text_localization_plan(p, policy=_policy())]
    assert TextLocalizationIssueKind.UNKNOWN_KIND_NOT_ROUTED in kinds


def test_validate_ui_needs_review_flag() -> None:
    p = _clean_plan([_decision(
        source_kind=TextTrackKind.UI,
        strategy=TextLocalizationStrategy.LOCALIZE_ANNOTATION,
        translated_text="保存",
        needs_review=False,  # 违规：UI 需授权确认必须 needs_review
    )])
    kinds = [i.kind for i in validate_text_localization_plan(p, policy=_policy())]
    assert TextLocalizationIssueKind.UI_NEEDS_LICENSE_REVIEW in kinds


def test_validate_redraw_missing_clean_plate() -> None:
    p = _clean_plan([_decision(clean_plate_request_id=None)])  # REDRAW 无 cp
    kinds = [i.kind for i in validate_text_localization_plan(p, policy=_policy())]
    assert TextLocalizationIssueKind.CLEAN_PLATE_MISSING in kinds


def test_validate_non_redraw_with_clean_plate_flagged() -> None:
    p = _clean_plan(
        [_decision(strategy=TextLocalizationStrategy.KEEP_AS_IS,
                     translated_text=None,
                     clean_plate_request_id="cp-0")],
        requests=[CleanPlateRequest(
            id="cp-0", source_track_id="tt-0", source_artifact_id="art",
            frame_start_ms=0, frame_end_ms=100,
            method=CleanPlateMethod.BACKGROUND_ESTIMATE,
        )],
    )
    kinds = [i.kind for i in validate_text_localization_plan(p, policy=_policy())]
    assert TextLocalizationIssueKind.CLEAN_PLATE_UNJUSTIFIED in kinds


def test_validate_translated_text_missing_for_redraw() -> None:
    p = _clean_plan([_decision(translated_text=None,
                                  clean_plate_request_id="cp-0")],
                       requests=[CleanPlateRequest(
                           id="cp-0", source_track_id="tt-0",
                           source_artifact_id="art",
                           frame_start_ms=0, frame_end_ms=100,
                           method=CleanPlateMethod.BACKGROUND_ESTIMATE)])
    kinds = [i.kind for i in validate_text_localization_plan(p, policy=_policy())]
    assert TextLocalizationIssueKind.TRANSLATED_TEXT_MISSING in kinds


def test_validate_translated_text_illegal_for_keep_as_is() -> None:
    p = _clean_plan([_decision(strategy=TextLocalizationStrategy.KEEP_AS_IS,
                                  translated_text="不该给")])
    kinds = [i.kind for i in validate_text_localization_plan(p, policy=_policy())]
    assert TextLocalizationIssueKind.TRANSLATED_TEXT_ILLEGAL in kinds


def test_validate_layout_overflow() -> None:
    p = _clean_plan([_decision(layout_expansion_ratio=1.5,
                                  clean_plate_request_id="cp-0")],
                       requests=[CleanPlateRequest(
                           id="cp-0", source_track_id="tt-0",
                           source_artifact_id="art",
                           frame_start_ms=0, frame_end_ms=100,
                           method=CleanPlateMethod.BACKGROUND_ESTIMATE)])
    kinds = [i.kind for i in validate_text_localization_plan(
        p, policy=_policy(max_expansion=1.3))]
    assert TextLocalizationIssueKind.LAYOUT_OVERFLOW in kinds


def test_validate_glossary_preserve_source_lost() -> None:
    gl = Glossary(
        id="g", source_language="zh-CN", target_language="en-US",
        entries=[GlossaryEntry(source_term="Qwen", target_term="Qwen",
                                  preserve_source=True)],
        created_at=_T0,
    )
    p = _clean_plan([_decision(source_text="Qwen 端侧模型",
                                  translated_text="on-device model",  # 丢了 Qwen
                                  clean_plate_request_id="cp-0")],
                       requests=[CleanPlateRequest(
                           id="cp-0", source_track_id="tt-0",
                           source_artifact_id="art",
                           frame_start_ms=0, frame_end_ms=100,
                           method=CleanPlateMethod.BACKGROUND_ESTIMATE)])
    kinds = [i.kind for i in validate_text_localization_plan(
        p, policy=_policy(), glossary=gl)]
    assert TextLocalizationIssueKind.GLOSSARY_MUST_KEEP_TERM_LOST in kinds


def test_is_valid_true_on_clean_plan() -> None:
    tts = TextTrackSet(
        id="tts", tracks=[_track(tid="c0", kind=TextTrackKind.CAPTION)],
        ocr_provider="fake", created_at=_T0,
    )
    p = plan_text_localization(
        tts, policy=_policy(), plan_id="pl", created_at=_T0,
        translations={"c0": "On-device 20 ms"},
    )
    assert is_valid_text_localization_plan(p, policy=_policy())
