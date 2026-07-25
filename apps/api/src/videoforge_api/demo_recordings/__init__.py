"""最小 zh/en Demo 录制（包资源）：驱动 Fake ASR/OCR/VLM 的回放数据。

**这不是真实引擎的输出**：真实 ASR/OCR/VLM 引擎 + 权重属停止条件（53 §10）。
provider 名对外如实写成 `fake-asr` / `fake-ocr` / `fake-vlm`，UI 一眼可辨。

数据是随包分发的 JSON（`src/videoforge_api/demo_recordings/*.json`），经 `importlib.resources`
读取——不依赖工作目录，打包后仍可用。
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from videoforge_contracts import TextObservation, Transcript
from videoforge_provider_sdk.asr import FakeASRProvider
from videoforge_provider_sdk.ocr import FakeOCRProvider
from videoforge_provider_sdk.vlm import FakeVLMProvider

DEMO_LANGUAGES: tuple[str, ...] = ("zh-CN", "en-US")


def _load(name: str) -> Any:
    text = resources.files(__package__).joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


@cache
def demo_transcript(language: str) -> Transcript:
    return Transcript.model_validate(_load(f"asr_{language}.json"))


@cache
def _demo_observations(language: str) -> tuple[TextObservation, ...]:
    return tuple(TextObservation.model_validate(o) for o in _load(f"ocr_{language}.json"))


@cache
def _demo_captions(language: str) -> dict[int, tuple[str, list[str], float]]:
    raw = _load(f"vlm_{language}.json")
    return {
        int(k): (v["caption"], list(v["labels"]), float(v["confidence"])) for k, v in raw.items()
    }


def load_transcripts(language: str) -> FakeASRProvider:
    """按语言给出 Fake ASR（只声明确有录制的语言，不假装支持其它语言）。"""
    return FakeASRProvider(
        name="fake-asr",
        languages=(language,),
        # 深拷贝：缓存的录制是共享对象，合同模型可变，绝不让调用方污染录制
        transcripts={language: demo_transcript(language).model_copy(deep=True)},
    )


def load_ocr_provider(language: str) -> FakeOCRProvider:
    return FakeOCRProvider(
        name="fake-ocr",
        observations=list(_demo_observations(language)),
        languages=(language,),
    )


def load_vlm_provider(language: str) -> FakeVLMProvider:
    return FakeVLMProvider(name="fake-vlm", captions=dict(_demo_captions(language)), version="1")


__all__ = [
    "DEMO_LANGUAGES",
    "demo_transcript",
    "load_ocr_provider",
    "load_transcripts",
    "load_vlm_provider",
]
