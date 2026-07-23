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
