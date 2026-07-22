"""测试辅助：加载录制转录 fixture（basename 唯一，避开 pytest 顶层冲突）。"""

from __future__ import annotations

import json
from pathlib import Path

from videoforge_contracts import Transcript

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "asr"


def load_transcript(name: str) -> Transcript:
    return Transcript.model_validate(
        json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    )


def recorded_transcripts() -> dict[str, Transcript]:
    return {"zh-CN": load_transcript("zh-CN"), "en-US": load_transcript("en-US")}
