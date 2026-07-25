from typing import Any

import pytest
from pydantic import ValidationError
from samples import SAMPLES

from videoforge_contracts import CONTRACTS

# highlight 候选的合法 11 项特征，用于构造嵌套负例
_HL_FEAT = {
    "hook_strength": 0.5, "self_containedness": 0.5, "information_density": 0.5,
    "surprise_or_conflict": 0.5, "emotional_energy": 0.5, "topic_relevance": 0.5,
    "visual_activity": 0.5, "speaker_prominence": 0.5, "ending_payoff": 0.5,
    "context_dependency": 0.2, "technical_defect": 0.1,
}


def _hl_candidate(**over: Any) -> dict[str, Any]:
    base = {"id": "hl", "start_ms": 0, "end_ms": 1000, "score": 0.1, "features": dict(_HL_FEAT)}
    base.update(over)
    return base


def _edit_op(**over: Any) -> dict[str, Any]:
    base = {"id": "op", "op": "KEEP", "source_start_ms": 0, "source_end_ms": 1000}
    base.update(over)
    return base


# (合同名, 字段覆写) —— 每条都必须被拒绝
INVALID_OVERRIDES: list[tuple[str, str, dict[str, Any]]] = [
    ("project", "未知字段被拒（extra=forbid）", {"unexpected_field": 1}),
    ("project", "目标语言不能为空", {"target_languages": []}),
    ("project", "非法状态枚举", {"status": "LAUNCHED"}),
    ("artifact", "sha256 必须是 64 位十六进制", {"sha256": "ZZZ"}),
    ("artifact", "size_bytes 不能为负", {"size_bytes": -1}),
    ("artifact", "存储后端受枚举约束", {"storage": {"backend": "ftp"}}),
    ("task-envelope", "attempt 从 1 起", {"attempt": 0}),
    ("task-envelope", "params 顶层禁明文凭据", {"params": {"cookie": "sessionid=abc"}}),
    (
        "task-envelope",
        "params 深层也禁明文凭据",
        {"params": {"douyin": {"session": {"access_token": "x"}}}},
    ),
    ("task-envelope", "驼峰凭据键同样被拒", {"params": {"accessToken": "x"}}),
    ("provider-descriptor", "capabilities 不能为空", {"capabilities": []}),
    ("provider-descriptor", "execution_location 受限", {"execution_location": "edge"}),
    ("provider-descriptor", "隔离等级受枚举约束", {"isolation_level": "L9"}),
    ("problem-detail", "status 必须是合法 HTTP 码", {"status": 42}),
    ("problem-detail", "title 不能为空", {"title": ""}),
    ("transcript", "未知字段被拒", {"unexpected_field": 1}),
    ("transcript", "主语言不能为空", {"language": ""}),
    ("transcript", "duration_ms 不能为负", {"duration_ms": -1}),
    (
        "transcript",
        "段 end_ms 不得早于 start_ms",
        {
            "segments": [
                {
                    "id": "bad",
                    "start_ms": 1000,
                    "end_ms": 500,
                    "language": "zh-CN",
                    "text": "x",
                    "confidence": 0.9,
                }
            ]
        },
    ),
    (
        "transcript",
        "词 end_ms 不得早于 start_ms",
        {
            "segments": [
                {
                    "id": "s",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "language": "zh-CN",
                    "text": "x",
                    "confidence": 0.9,
                    "words": [{"text": "w", "start_ms": 900, "end_ms": 800, "confidence": 0.9}],
                }
            ]
        },
    ),
    ("text-track-set", "未知字段被拒", {"unexpected_field": 1}),
    ("text-track-set", "ocr_provider 不能为空", {"ocr_provider": ""}),
    (
        "text-track-set",
        "轨 end_ms 不得早于 start_ms",
        {"tracks": [{"id": "x", "text": "t", "start_ms": 1000, "end_ms": 500, "confidence": 0.9}]},
    ),
    (
        "text-track-set",
        "bbox 不得超出画面",
        {
            "tracks": [
                {
                    "id": "x",
                    "text": "t",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "confidence": 0.9,
                    "observations": [
                        {
                            "frame_time_ms": 0,
                            "bbox": {"x": 0.9, "y": 0.1, "w": 0.5, "h": 0.1},
                            "text": "t",
                            "confidence": 0.9,
                        }
                    ],
                }
            ]
        },
    ),
    ("visual-analysis", "未知字段被拒", {"unexpected_field": 1}),
    ("visual-analysis", "sampling_policy 不能为空", {"sampling_policy": ""}),
    (
        "visual-analysis",
        "帧 reasons 不能为空",
        {"frames": [{"frame_time_ms": 0, "reasons": []}]},
    ),
    (
        "visual-analysis",
        "帧时间不能为负",
        {"frames": [{"frame_time_ms": -1, "reasons": ["KEYFRAME"]}]},
    ),
    ("video-blueprint", "未知字段被拒", {"unexpected_field": 1}),
    ("video-blueprint", "duration_ms 必须 > 0", {"duration_ms": 0}),
    (
        "video-blueprint",
        "Claim 必须至少一条证据",
        {"claims": [{"id": "c", "text": "x", "evidence": []}]},
    ),
    (
        "video-blueprint",
        "节拍 end_ms 不得早于 start_ms",
        {"rhetorical_beats": [{"id": "r", "kind": "HOOK", "start_ms": 1000, "end_ms": 500}]},
    ),
    ("creative-opportunity", "未知字段被拒", {"unexpected_field": 1}),
    ("creative-opportunity", "rationale 不能为空", {"rationale": ""}),
    ("creative-brief", "未知字段被拒", {"unexpected_field": 1}),
    ("creative-brief", "duration_target_ms 必须 > 0", {"duration_target_ms": 0}),
    ("creative-brief", "angle 不能为空", {"angle": ""}),
    (
        "creative-brief",
        "visual_mix 四类之和须 ≈ 1",
        {"visual_mix": {"talking_head": 0.5, "screen_demo": 0.5, "broll": 0.5, "info_card": 0.5}},
    ),
    ("claim-table", "未知字段被拒", {"unexpected_field": 1}),
    (
        "claim-table",
        "条目证据不能为空",
        {"entries": [{"claim_id": "c", "text": "x", "evidence": []}]},
    ),
    ("beat-template", "未知字段被拒", {"unexpected_field": 1}),
    ("beat-template", "duration_target_ms 必须 > 0", {"duration_target_ms": 0}),
    (
        "beat-template",
        "槽位 end_ms 不得早于 start_ms",
        {"slots": [{"id": "s", "role": "HOOK", "start_ms": 1000, "end_ms": 500,
                    "target_duration_ms": 0}]},
    ),
    ("script-version", "未知字段被拒", {"unexpected_field": 1}),
    (
        "script-version",
        "句子 text 不能为空",
        {"sentences": [{"id": "s", "beat_slot_id": "slot-0", "role": "HOOK", "text": "",
                        "target_duration_ms": 100, "language": "zh-CN"}]},
    ),
    ("highlight-set", "未知字段被拒", {"unexpected_field": 1}),
    ("highlight-set", "id 不能为空", {"id": ""}),
    ("highlight-set", "candidate end<start 被拒",
     {"candidates": [_hl_candidate(start_ms=5000, end_ms=1000)]}),
    ("highlight-set", "特征子分越界被拒",
     {"candidates": [_hl_candidate(features={**_HL_FEAT, "hook_strength": 1.5})]}),
    ("highlight-set", "predicted_retention 越界被拒",
     {"candidates": [_hl_candidate(predicted_retention=1.5)]}),
    ("highlight-set", "非法理由码被拒",
     {"candidates": [_hl_candidate(reason_codes=["NOT_A_REASON"])]}),
    ("reedit-plan", "未知字段被拒", {"unexpected_field": 1}),
    ("reedit-plan", "kept_duration_ms 不能为负", {"kept_duration_ms": -1}),
    ("reedit-plan", "op end<start 被拒",
     {"ops": [_edit_op(source_start_ms=5000, source_end_ms=1000)]}),
    ("reedit-plan", "非法操作枚举被拒", {"ops": [_edit_op(op="FROBNICATE")]}),
    ("reedit-plan", "SPEED 倍率须 >0", {"ops": [_edit_op(op="SPEED", speed=0)]}),
    ("reedit-plan", "非法连续性枚举被拒",
     {"continuity": [{"kind": "NOPE", "at_ms": 0, "detail": "x"}]}),
    ("asset-plan", "未知字段被拒", {"unexpected_field": 1}),
    ("asset-plan", "slot end_ms<start_ms 被拒", {"slots": [{
        "slot_id": "s", "start_ms": 5000, "end_ms": 1000, "role": "B_ROLL",
        "query": "q", "composition": {"aspect_ratio": "9:16", "safe_area": "center"},
        "allowed_sources": ["SOURCE"],
    }]}),
    ("asset-plan", "allowed_sources 不能为空", {"slots": [{
        "slot_id": "s", "start_ms": 0, "end_ms": 1000, "role": "B_ROLL",
        "query": "q", "composition": {"aspect_ratio": "9:16", "safe_area": "center"},
        "allowed_sources": [],
    }]}),
    ("asset-plan", "非法 AssetRole 被拒", {"slots": [{
        "slot_id": "s", "start_ms": 0, "end_ms": 1000, "role": "NOT_A_ROLE",
        "query": "q", "composition": {"aspect_ratio": "9:16", "safe_area": "center"},
        "allowed_sources": ["SOURCE"],
    }]}),
    ("asset-plan", "resolved usage_end<start 被拒", {"resolved": [{
        "slot_id": "s", "asset_id": "a", "source": "OWN_LIBRARY",
        "license": {"type": "OWNED", "holder": "h"},
        "query": "q", "usage_start_ms": 5000, "usage_end_ms": 1000, "match_score": 0.5,
    }]}),
    ("asset-plan", "非法 AssetLicenseType 被拒", {"resolved": [{
        "slot_id": "s", "asset_id": "a", "source": "OWN_LIBRARY",
        "license": {"type": "PIRATED", "holder": "h"},
        "query": "q", "usage_start_ms": 0, "usage_end_ms": 1000, "match_score": 0.5,
    }]}),
    ("creative-timeline", "未知字段被拒", {"unexpected_field": 1}),
    ("creative-timeline", "rate 必须 > 0", {"rate": 0}),
    ("creative-timeline", "duration.rate 与 timeline.rate 必须一致",
     {"duration": {"value": 100, "rate": 25}}),  # sample rate=30
    ("creative-timeline", "非法 TrackKind 被拒", {"tracks": [{
        "id": "t", "kind": "NOT_A_TRACK", "segments": [],
    }]}),
    ("creative-timeline", "RationalTimeRange start/duration rate 不一致",
     {"tracks": [{"id": "t", "kind": "V1_PRIMARY_VIDEO", "segments": [{
         "id": "s", "time_range": {
             "start": {"value": 0, "rate": 30},
             "duration": {"value": 100, "rate": 25},
         },
     }]}]}),
    ("creative-timeline", "RationalTime value 不能为负",
     {"duration": {"value": -1, "rate": 30}}),
    ("render-manifest", "未知字段被拒", {"unexpected_field": 1}),
    ("render-manifest", "argv 元素含 shell 元字符被拒",
     {"render_graph": {**SAMPLES["render-manifest"].model_dump()["render_graph"],
                        "args": ["ffmpeg", "-y", "$(rm -rf /)", "/output/final.mp4"]}}),
    ("render-manifest", "空 argv token 被拒",
     {"render_graph": {**SAMPLES["render-manifest"].model_dump()["render_graph"],
                        "args": ["ffmpeg", "", "/output/final.mp4"]}}),
    ("render-manifest", "output_path 含 shell 元字符被拒",
     {"render_graph": {**SAMPLES["render-manifest"].model_dump()["render_graph"],
                        "output_path": "/output/`whoami`.mp4"}}),
    ("render-manifest", "input.sha256 非 64 hex 被拒",
     {"render_graph": {**SAMPLES["render-manifest"].model_dump()["render_graph"],
                        "inputs": [{"asset_id": "a", "sha256": "ZZZ",
                                    "resolved_path": "/s/a.mp4"}]}}),
    ("render-manifest", "output_digest 非 64 hex 被拒", {"output_digest": "shortdigest"}),
    ("render-manifest", "非法 RenderStage 被拒", {"stage": "DRAFT"}),
    ("remotion-render-manifest", "未知字段被拒", {"unexpected_field": 1}),
    ("remotion-render-manifest", "props 键非法（非 JS 标识符）被拒",
     {"request": {**SAMPLES["remotion-render-manifest"].model_dump()["request"],
                    "props": [{"key": "9invalid", "value": "x"}]}}),
    ("remotion-render-manifest", "props 值含 shell 元字符被拒",
     {"request": {**SAMPLES["remotion-render-manifest"].model_dump()["request"],
                    "props": [{"key": "title", "value": "hello$(rm -rf /)"}]}}),
    ("remotion-render-manifest", "entry_component_path 含 shell 元字符被拒",
     {"request": {**SAMPLES["remotion-render-manifest"].model_dump()["request"],
                    "entry_component_path": "/staging/$(id).tsx"}}),
    ("remotion-render-manifest", "fps 必须 >0",
     {"request": {**SAMPLES["remotion-render-manifest"].model_dump()["request"], "fps": 0}}),
    ("remotion-render-manifest", "width 超上限 8192 被拒",
     {"request": {**SAMPLES["remotion-render-manifest"].model_dump()["request"], "width": 10000}}),
    ("remotion-render-manifest", "非法 RemotionComposition 被拒",
     {"request": {**SAMPLES["remotion-render-manifest"].model_dump()["request"],
                    "composition": "UNKNOWN_COMP"}}),
    ("remotion-render-manifest", "props 键重复被拒",
     {"request": {**SAMPLES["remotion-render-manifest"].model_dump()["request"],
                    "props": [{"key": "same", "value": 1}, {"key": "same", "value": 2}]}}),
    ("qa-report", "未知字段被拒", {"unexpected_field": 1}),
    ("qa-report", "非法 QASeverity 被拒",
     {"findings": [{"id": "f", "kind": "BLACK_FRAME", "severity": "PANIC", "at_ms": 0}]}),
    ("qa-report", "非法 QAFindingKind 被拒",
     {"findings": [{"id": "f", "kind": "NOT_A_KIND", "severity": "BLOCKER", "at_ms": 0}]}),
    ("qa-report", "finding at_ms 不能为负",
     {"findings": [{"id": "f", "kind": "BLACK_FRAME", "severity": "MAJOR", "at_ms": -1}]}),
    ("qa-report", "finding duration_ms 不能为负",
     {"findings": [{"id": "f", "kind": "BLACK_FRAME", "severity": "MAJOR", "at_ms": 0,
                      "duration_ms": -1}]}),
    ("qa-report", "finding id 重复被拒",
     {"findings": [
         {"id": "same", "kind": "BLACK_FRAME", "severity": "MAJOR", "at_ms": 0},
         {"id": "same", "kind": "FROZEN_FRAME", "severity": "MINOR", "at_ms": 100},
     ]}),
    ("qa-report", "measured_duration_ms 不能为负", {"measured_duration_ms": -1}),
    # 本地化：CanonicalSentence 时间跨度倒序被拒
    ("canonical-script", "sentence 时间跨度倒序被拒",
     {"sentences": [{
         "id": "cs-x", "beat_slot_id": "b", "role": "HOOK",
         "source_language": "zh-CN", "source_text": "x", "semantic_intent": "i",
         "source_time_range_start_ms": 100, "source_time_range_end_ms": 0,
         "target_duration_ms": 100,
     }]}),
    # 本地化：CanonicalSentence source_text 空
    ("canonical-script", "sentence source_text 空被拒",
     {"sentences": [{
         "id": "cs-x", "beat_slot_id": "b", "role": "HOOK",
         "source_language": "zh-CN", "source_text": "", "semantic_intent": "i",
         "source_time_range_start_ms": 0, "source_time_range_end_ms": 100,
         "target_duration_ms": 100,
     }]}),
    # 本地化：CanonicalSentence edit_flexibility 越界（>1）
    ("canonical-script", "edit_flexibility 越界被拒",
     {"sentences": [{
         "id": "cs-x", "beat_slot_id": "b", "role": "HOOK",
         "source_language": "zh-CN", "source_text": "x", "semantic_intent": "i",
         "source_time_range_start_ms": 0, "source_time_range_end_ms": 100,
         "target_duration_ms": 100, "edit_flexibility": 1.2,
     }]}),
    # 术语表：GlossaryEntry preserve_source=True 但 target_term ≠ source
    ("glossary", "preserve_source 与 target_term 不一致被拒",
     {"entries": [{"source_term": "Qwen", "target_term": "QwenX",
                     "preserve_source": True}]}),
    # 术语表：entries source_term 重复被拒
    ("glossary", "entries source_term 重复被拒",
     {"entries": [
         {"source_term": "端侧", "target_term": "on-device"},
         {"source_term": "端侧", "target_term": "edge"},
     ]}),
    # TRA 结果：semantic_similarity 越界（>1）
    ("translate-reflect-adapt-result", "semantic_similarity 越界被拒",
     {"semantic_similarity": 1.05}),
    # TRA 结果：adapted_text 空被拒
    ("translate-reflect-adapt-result", "adapted_text 空被拒", {"adapted_text": ""}),
    # LocalizationVariant：target_language 空被拒
    ("localization-variant", "target_language 空被拒", {"target_language": ""}),
    # LocalizedSentence：semantic_similarity 越界（<0）
    ("localization-variant", "sentence semantic_similarity 负值被拒",
     {"sentences": [{
         "id": "ls-x", "canonical_sentence_id": "cs-0", "target_language": "en-US",
         "text": "x", "duration_estimate_ms": 100, "semantic_similarity": -0.1,
     }]}),
    # 字幕：SubtitleTemplate 无任何阅读速度上限 → 拒
    ("subtitle-template", "无阅读速度上限被拒", {
        "cjk_chars_per_sec": None, "en_chars_per_sec": None,
        "en_words_per_sec": None,
    }),
    # 字幕：SubtitleTemplate max_lines_per_cue > 2
    ("subtitle-template", "max_lines_per_cue 超过 2 被拒", {"max_lines_per_cue": 3}),
    # 字幕：SubtitleTemplate min_cue_duration_ms > max_cue_duration_ms
    ("subtitle-template", "min > max cue duration 被拒",
     {"min_cue_duration_ms": 7000, "max_cue_duration_ms": 5000}),
    # 字幕：SafeAreaSpec left ≥ right
    ("subtitle-template", "safe_area left ≥ right 被拒",
     {"safe_area": {"left_min_pct": 60, "right_max_pct": 40}}),
    # 字幕：SafeAreaSpec top ≥ bottom
    ("subtitle-template", "safe_area top ≥ bottom 被拒",
     {"safe_area": {"top_min_pct": 90, "bottom_max_pct": 80}}),
    # 字幕：cue 时间倒序
    ("subtitle-track", "cue 时间倒序被拒", {
        "cues": [{
            "id": "c-x", "start_ms": 5000, "end_ms": 1000,
            "lines": [{"text": "x", "start_ms": 0, "end_ms": 100,
                        "language": "zh-CN"}],
        }],
    }),
    # 字幕：cue.lines 空数组
    ("subtitle-track", "cue lines 为空被拒", {
        "cues": [{"id": "c-x", "start_ms": 0, "end_ms": 1000, "lines": []}],
    }),
    # 字幕：SubtitleLine text 空
    ("subtitle-track", "line text 空被拒", {
        "cues": [{"id": "c-x", "start_ms": 0, "end_ms": 1000, "lines": [
            {"text": "", "start_ms": 0, "end_ms": 1000, "language": "zh-CN"},
        ]}],
    }),
    # 字幕：SubtitleWord end < start
    ("subtitle-track", "word 时间倒序被拒", {
        "cues": [{"id": "c-x", "start_ms": 0, "end_ms": 1000, "lines": [{
            "text": "x", "start_ms": 0, "end_ms": 1000, "language": "zh-CN",
            "words": [{"text": "x", "start_ms": 500, "end_ms": 200}],
        }]}],
    }),
    # 画面文字：AUTHORIZED_INPAINT 缺 license_ref
    ("text-localization-plan", "AUTHORIZED_INPAINT 无 license_ref 被拒", {
        "clean_plate_requests": [{
            "id": "cp-x", "source_track_id": "tt-0",
            "source_artifact_id": "art-0",
            "frame_start_ms": 0, "frame_end_ms": 1000,
            "method": "AUTHORIZED_INPAINT",
        }],
    }),
    # 画面文字：CleanPlateRequest 时间倒序
    ("text-localization-plan", "clean plate 时间倒序被拒", {
        "clean_plate_requests": [{
            "id": "cp-x", "source_track_id": "tt-0",
            "source_artifact_id": "art-0",
            "frame_start_ms": 1000, "frame_end_ms": 500,
            "method": "BACKGROUND_ESTIMATE",
        }],
    }),
    # 画面文字：decision 引用不存在的 clean_plate_request_id
    ("text-localization-plan", "decision 引用未知 clean_plate id 被拒", {
        "decisions": [{
            "source_track_id": "tt-x", "source_text": "x",
            "source_kind": "CAPTION", "target_language": "en-US",
            "strategy": "REDRAW", "translated_text": "y",
            "clean_plate_request_id": "cp-ghost",
            "rationale": "ok",
        }],
    }),
    # 画面文字：同一 source_track_id 出现两次
    ("text-localization-plan", "重复的 source_track_id 被拒", {
        "decisions": [
            {"source_track_id": "same", "source_text": "a",
              "source_kind": "CAPTION", "target_language": "en-US",
              "strategy": "SKIP", "rationale": "one"},
            {"source_track_id": "same", "source_text": "b",
              "source_kind": "UI", "target_language": "en-US",
              "strategy": "SKIP", "rationale": "two"},
        ],
    }),
    # 画面文字：max_layout_expansion_ratio ≤ 1
    ("text-localization-plan", "policy expansion ratio ≤ 1 不属于本合同（by design "
     "policy 独立），此处只测 decision.rationale 空", {
        "decisions": [{
            "source_track_id": "tt-x", "source_text": "x",
            "source_kind": "CAPTION", "target_language": "en-US",
            "strategy": "SKIP", "rationale": "",  # 空
        }],
    }),
    # TTS：CLONED voice 无 sample_source_ref 被拒（§7 硬红线）
    ("voice-profile", "CLONED 无 sample_source_ref 被拒", {
        "voice_kind": "CLONED", "sample_source_ref": None,
        "consent_ref": "consent://x",
    }),
    # TTS：CLONED voice 无 consent_ref 被拒
    ("voice-profile", "CLONED 无 consent_ref 被拒", {
        "voice_kind": "CLONED",
        "sample_source_ref": "artifact://sample.wav",
        "consent_ref": None,
    }),
    # TTS：非法 VoiceLicenseStatus
    ("voice-profile", "非法 license_status 被拒",
     {"license_status": "APPROVED"}),
    # TTS：display_name 空
    ("voice-profile", "display_name 空被拒", {"display_name": ""}),
    # TTS：非法 voice_kind
    ("voice-profile", "非法 voice_kind 被拒", {"voice_kind": "SAMPLED"}),
    # TTS：pronunciation-lexicon entries surface 重复
    ("pronunciation-lexicon", "entries surface 重复被拒", {
        "entries": [
            {"surface": "Qwen", "pronunciation": "/a/"},
            {"surface": "Qwen", "pronunciation": "/b/"},
        ],
    }),
    # TTS：word_timing end < start
    ("tts-manifest", "word_timing 时间倒序被拒", {
        "word_timings": [{"text": "x", "start_ms": 500, "end_ms": 100}],
    }),
    # TTS：manifest text_hash 空
    ("tts-manifest", "text_hash 空被拒", {"text_hash": ""}),
    # TTS：manifest speed_used 非正
    ("tts-manifest", "speed_used ≤ 0 被拒", {"speed_used": 0.0}),
    # 时长拟合：decisions 内 sentence_id 重复
    ("duration-fit-plan", "重复 sentence_id 被拒", {
        "decisions": [
            {"sentence_id": "a", "estimated_ms": 3000, "target_ms": 3000,
             "final_ratio": 1.0, "status": "OK_UNCHANGED", "rationale": "x"},
            {"sentence_id": "a", "estimated_ms": 3100, "target_ms": 3000,
             "final_ratio": 1.03, "status": "OK_FITTED", "fit_method": "TTS_SPEED",
             "rationale": "y"},
        ],
    }),
    # 时长拟合：final_ratio 非正
    ("duration-fit-plan", "final_ratio ≤ 0 被拒", {
        "decisions": [
            {"sentence_id": "a", "estimated_ms": 3000, "target_ms": 3000,
             "final_ratio": 0.0, "status": "OK_UNCHANGED", "rationale": "x"},
        ],
    }),
    # 时长拟合：target_ms 非正
    ("duration-fit-plan", "target_ms ≤ 0 被拒", {
        "decisions": [
            {"sentence_id": "a", "estimated_ms": 3000, "target_ms": 0,
             "final_ratio": 1.0, "status": "OK_UNCHANGED", "rationale": "x"},
        ],
    }),
    # 音频合成：tracks id 重复
    ("audio-mix-plan", "tracks id 重复被拒", {
        "tracks": [
            {"id": "t", "kind": "VOICE_DUB", "start_ms": 0, "end_ms": 100},
            {"id": "t", "kind": "MUSIC", "start_ms": 0, "end_ms": 100},
        ],
    }),
    # 音频合成：ducked_by 指向不存在的轨
    ("audio-mix-plan", "ducked_by 悬空被拒", {
        "tracks": [
            {"id": "dub", "kind": "VOICE_DUB", "start_ms": 0, "end_ms": 100},
            {"id": "m", "kind": "MUSIC", "start_ms": 0, "end_ms": 100,
             "ducked_by": "ghost"},
        ],
    }),
    # 音频合成：轨自己 Ducking 自己
    ("audio-mix-plan", "自 Ducking 被拒", {
        "tracks": [
            {"id": "dub", "kind": "VOICE_DUB", "start_ms": 0, "end_ms": 100,
             "ducked_by": "dub"},
        ],
    }),
    # 音频合成：track end < start
    ("audio-mix-plan", "track end < start 被拒", {
        "tracks": [
            {"id": "t", "kind": "VOICE_DUB", "start_ms": 500, "end_ms": 100},
        ],
    }),
    # 音频合成：True Peak 硬顶不能为正
    ("audio-mix-plan", "true_peak_max_dbtp > 0 被拒",
     {"loudness_target": {"true_peak_max_dbtp": 1.0}}),
    # 口型：GPU_SYNTHESIS 只能用于合格片段
    ("lipsync-plan", "GPU_SYNTHESIS 用于不合格片段被拒", {
        "decisions": [{
            "segment_id": "a", "start_ms": 0, "end_ms": 100, "eligible": False,
            "ineligible_reasons": ["MULTIPLE_FACES"], "method": "GPU_SYNTHESIS",
            "rationale": "x",
        }],
    }),
    # 口型：eligible=False 必须记录原因
    ("lipsync-plan", "不合格无原因被拒", {
        "decisions": [{
            "segment_id": "a", "start_ms": 0, "end_ms": 100, "eligible": False,
            "method": "KEEP_UNSYNCED", "rationale": "x",
        }],
    }),
    # 口型：end < start
    ("lipsync-plan", "decision end < start 被拒", {
        "decisions": [{
            "segment_id": "a", "start_ms": 500, "end_ms": 100, "eligible": True,
            "method": "GPU_SYNTHESIS", "rationale": "x",
        }],
    }),
    # 口型：segment_id 重复
    ("lipsync-plan", "重复 segment_id 被拒", {
        "decisions": [
            {"segment_id": "a", "start_ms": 0, "end_ms": 100, "eligible": True,
             "method": "GPU_SYNTHESIS", "rationale": "x"},
            {"segment_id": "a", "start_ms": 100, "end_ms": 200, "eligible": True,
             "method": "GPU_SYNTHESIS", "rationale": "y"},
        ],
    }),
    # 口型：criteria min_duration > max_duration
    ("lipsync-plan", "criteria 时长下界 > 上界被拒",
     {"criteria": {"min_duration_ms": 5000, "max_duration_ms": 1000}}),
    # 口型：QA 分数超 [0,1]
    ("lipsync-plan", "QA 分数越界被拒", {
        "decisions": [{
            "segment_id": "a", "start_ms": 0, "end_ms": 100, "eligible": True,
            "method": "GPU_SYNTHESIS", "rationale": "x",
            "qa": {"boundary_score": 1.5, "skin_tone_score": 0.9,
                   "motion_score": 0.9, "identity_score": 0.9, "passed": True},
        }],
    }),
    # 本地化审核：pass_or_block=True 不能与 BLOCKER 并存（发布门红线）
    ("localization-qa-report", "pass 却含 BLOCKER 被拒", {
        "pass_or_block": True,
        "findings": [{
            "sentence_id": "s", "check": "NUMBER_CONSISTENCY", "severity": "BLOCKER",
            "detail": "数字不一致",
        }],
    }),
    # 本地化审核：EDITED 必须携带 edited_text
    ("localization-review", "EDITED 无 edited_text 被拒", {
        "decisions": [{"sentence_id": "s", "state": "EDITED"}],
    }),
    # 本地化审核：非 EDITED 不能携带 edited_text
    ("localization-review", "非 EDITED 带 edited_text 被拒", {
        "decisions": [{
            "sentence_id": "s", "state": "APPROVED", "edited_text": "x",
        }],
    }),
    # 本地化审核：sentence_id 重复
    ("localization-review", "重复 sentence_id 被拒", {
        "decisions": [
            {"sentence_id": "s", "state": "APPROVED"},
            {"sentence_id": "s", "state": "PENDING"},
        ],
    }),
    # 审核：signature 不能为空
    ("review-decision", "signature 空被拒", {"signature": ""}),
    # 审核：entity_version 必须 ≥ 1
    ("review-decision", "entity_version < 1 被拒", {"entity_version": 0}),
    # 审核：content_digest 不能为空
    ("review-decision", "content_digest 空被拒", {"content_digest": ""}),
    # 模板受信：recent_fatal_count 不能超过 recent_window
    ("template-trust-state", "recent_fatal 超窗口被拒", {
        "stats": {
            "approved_render_count": 5, "recent_fatal_count": 99,
            "recent_error_rate": 0.0, "qa_meets_standard": True,
            "publish_success_ok": True, "duplicate_publish_ok": True,
            "owner_approved": True,
        },
        "criteria": {"recent_window": 20},
    }),
    # 模板受信：error_rate 超 [0,1]
    ("template-trust-state", "error_rate 越界被拒", {
        "stats": {
            "approved_render_count": 5, "recent_fatal_count": 0,
            "recent_error_rate": 1.5, "qa_meets_standard": True,
            "publish_success_ok": True, "duplicate_publish_ok": True,
            "owner_approved": True,
        },
    }),
    # 预检：min_width > max_width
    ("platform-publish-spec", "min_width > max_width 被拒",
     {"min_width": 2000, "max_width": 1080}),
    # 预检：min_duration > max_duration
    ("platform-publish-spec", "min_duration > max_duration 被拒",
     {"min_duration_ms": 700000, "max_duration_ms": 600000}),
    # 预检：allowed_aspect_ratios 不能空
    ("platform-publish-spec", "allowed_aspect_ratios 空被拒",
     {"allowed_aspect_ratios": []}),
    # 预检：publishable=True 不能与 ERROR/FATAL 并存
    ("preflight-report", "publishable 却含 ERROR 被拒", {
        "publishable": True,
        "findings": [{
            "check": "FILE_SIZE", "severity": "ERROR", "detail": "文件过大",
        }],
    }),
    # 连接器能力：max_file_size_bytes 若给必须 > 0
    ("publish-connector-capability", "max_file_size_bytes ≤ 0 被拒",
     {"max_file_size_bytes": 0}),
    # 发布任务：SUCCEEDED 必须携带 external_post_id
    ("publish-job", "SUCCEEDED 无 external_post_id 被拒",
     {"state": "SUCCEEDED", "external_post_id": None}),
    # 发布任务：SUCCEEDED_RECONCILED 同理
    ("publish-job", "SUCCEEDED_RECONCILED 无 external_post_id 被拒",
     {"state": "SUCCEEDED_RECONCILED", "external_post_id": None}),
    # 发布任务：idempotency_key 不能空
    ("publish-job", "idempotency_key 空被拒", {"idempotency_key": ""}),
    # 发布任务：attempt 必须 ≥ 1
    ("publish-job", "attempt < 1 被拒", {
        "attempts": [{"attempt": 0, "request_digest": "r",
                       "at": "2026-07-25T00:00:00Z"}],
    }),
    # 账号：credential_ref 像明文 JWT 被拒（§8 无 secret 红线）
    ("platform-account", "credential_ref 像 JWT 被拒",
     {"credential_ref": "eyJhbGciOiJIUzI1NiJ9.payload.sig"}),
    # 账号：credential_ref 像 Bearer token 被拒
    ("platform-account", "credential_ref 像 Bearer 被拒",
     {"credential_ref": "Bearer sk-secret-123"}),
    # 账号：credential_ref 不能空
    ("platform-account", "credential_ref 空被拒", {"credential_ref": ""}),
    # 账号：前缀包裹的 JWT 也被拒（verifier 揭示的嵌入绕过——子串扫描）
    ("platform-account", "handle 前缀包裹的 JWT 被拒",
     {"credential_ref": "ch-eyJhbGciOiJIUzI1NiJ9.payload.sig"}),
    ("platform-account", "内嵌 refresh_token 被拒",
     {"credential_ref": "handle_refresh_token_abc"}),
    ("performance-snapshot", "未知字段被拒", {"unexpected_field": 1}),
    ("performance-snapshot", "views 为负被拒", {"views": -1}),
    ("performance-snapshot", "completion_rate > 1 被拒", {"completion_rate": 1.5}),
    ("performance-snapshot", "age_hours 为负被拒", {"age_hours": -1.0}),
    ("performance-snapshot", "source_confidence > 1 被拒", {"source_confidence": 1.2}),
    ("snapshot-schedule", "planned_ages 为空被拒", {"planned_ages_hours": []}),
    ("snapshot-schedule", "planned_ages 重复被拒", {"planned_ages_hours": [1.0, 1.0]}),
    ("snapshot-schedule", "captured 非 planned 子集被拒",
     {"planned_ages_hours": [1.0, 3.0], "captured_ages_hours": [6.0]}),
    ("metrics-connector-capability", "非法 MetricField 被拒",
     {"provided_fields": ["FOO"]}),
    ("metrics-connector-capability", "min_seconds 为负被拒",
     {"min_seconds_between_calls": -1}),
    ("video-performance-record", "account_id 空被拒", {"account_id": ""}),
    ("video-performance-record", "publish_hour 超 23 被拒",
     {"features": {"publish_hour": 24}}),
    ("account-baseline", "sample_count 为负被拒",
     {"entries": [{"age_hours": 24.0, "metric": "VIEWS", "sample_count": -1}]}),
    ("performance-dashboard", "min_samples < 1 被拒", {"min_samples": 0}),
    ("performance-dashboard", "有相对值却无基线中位数被拒",
     {"baseline": {"age_hours": 24.0, "metric": "VIEWS", "median": None,
                    "sample_count": 0},
      "group_stats": [{"dimension": "TEMPLATE", "value": "t", "age_hours": 24.0,
                        "metric": "VIEWS", "sample_count": 3,
                        "median_relative": 1.2, "enough_samples": False}]}),
    ("performance-dashboard", "非法 GroupDimension 被拒",
     {"group_stats": [{"dimension": "AUTHOR", "value": "x", "age_hours": 24.0,
                        "metric": "VIEWS", "sample_count": 0,
                        "enough_samples": False}]}),
    ("exporter-report", "未知字段被拒", {"unexpected_field": 1}),
    ("exporter-report", "非法 ExporterKind 被拒",
     {"entries": [{"kind": "PREMIERE_XML", "status": "OK"}]}),
    ("exporter-report", "非法 ExporterStatus 被拒",
     {"entries": [{"kind": "OTIO_FILE", "status": "SUCCESS"}]}),
    ("exporter-report", "output_path 含 shell 元字符被拒",
     {"entries": [{"kind": "OTIO_FILE", "status": "OK",
                     "output_path": "/output/$(id).otio"}]}),
    ("exporter-report", "bytes_written 不能为负",
     {"entries": [{"kind": "OTIO_FILE", "status": "OK",
                     "output_path": "/output/tl.otio", "bytes_written": -1}]}),
]


@pytest.mark.parametrize(
    ("name", "reason", "overrides"),
    INVALID_OVERRIDES,
    ids=[f"{name}:{reason}" for name, reason, _ in INVALID_OVERRIDES],
)
def test_invalid_payload_rejected(name: str, reason: str, overrides: dict[str, Any]) -> None:
    payload = SAMPLES[name].model_dump(mode="json")
    payload.update(overrides)
    with pytest.raises(ValidationError):
        CONTRACTS[name].model_validate(payload)


def test_task_envelope_error_points_to_offending_key() -> None:
    payload = SAMPLES["task-envelope"].model_dump(mode="json")
    payload["params"] = {"platform": {"cookie_jar": "..."}}
    with pytest.raises(ValidationError, match="params.platform.cookie_jar"):
        CONTRACTS["task-envelope"].model_validate(payload)


def test_llm_like_param_keys_are_not_false_positives() -> None:
    payload = SAMPLES["task-envelope"].model_dump(mode="json")
    payload["params"] = {"max_tokens": 512, "tokenizer": "bpe", "temperature": 0.7}
    parsed = CONTRACTS["task-envelope"].model_validate(payload)
    assert parsed.model_dump()["params"]["max_tokens"] == 512
