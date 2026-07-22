from typing import Any

import pytest
from pydantic import ValidationError
from samples import SAMPLES

from videoforge_contracts import CONTRACTS

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
