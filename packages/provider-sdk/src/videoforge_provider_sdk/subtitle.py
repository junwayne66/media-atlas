"""Forced Alignment 端口 + Fake（docs/modules/43 §5.2）。

原声字幕跟 ASR 词级时间；配音字幕跟 TTS 生成后的 forced alignment，**不复用原时间**。
真实对齐引擎（whisperX / MFA / gentle）需模型权重，属停止条件延后：
- UnconfiguredForcedAlignmentProvider 恒返 UNCONFIGURED
- FakeForcedAlignmentProvider 按字符/词长度在 [start,end] 内均分（可复现，无随机）。
  仅供下游 pipeline 开发；不产生"看起来真实"的高置信度值——每 word confidence 固定 0.5。
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import SubtitleWord

_EN_TOKEN_RE = re.compile(r"\S+")


class ForcedAlignmentStatus(StrEnum):
    OK = "OK"
    FAILED = "FAILED"
    UNCONFIGURED = "UNCONFIGURED"


class ForcedAlignmentErrorCode(StrEnum):
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    AUDIO_MISSING = "AUDIO_MISSING"
    LANGUAGE_UNSUPPORTED = "LANGUAGE_UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ForcedAlignmentRequest:
    """一次对齐调用：给定文本 + 语言 + 音频区间（audio_artifact_id + start/end）→ 词级时间。"""

    text: str
    language: str
    start_ms: int
    end_ms: int
    audio_artifact_id: str | None = None


@dataclass(frozen=True)
class ForcedAlignmentResult:
    status: ForcedAlignmentStatus
    words: list[SubtitleWord] = field(default_factory=list)
    provider: str | None = None
    error_code: ForcedAlignmentErrorCode | None = None
    error_detail: str | None = None


@runtime_checkable
class ForcedAlignmentProvider(Protocol):
    """给一段文本对齐到音频区间，返回词级时间。TTS 后与 ASR 后统一走此端口。"""

    name: str
    execution_location: str  # local / cloud

    def align(self, request: ForcedAlignmentRequest) -> ForcedAlignmentResult: ...

    def health_check(self) -> ForcedAlignmentResult: ...


class UnconfiguredForcedAlignmentProvider:
    """诚实占位：无真实对齐模型，绝不"猜"。返回 UNCONFIGURED，上层路由至人工/回退。"""

    def __init__(
        self, *, name: str = "align.unconfigured", execution_location: str = "local"
    ) -> None:
        self.name = name
        self.execution_location = execution_location

    def align(self, request: ForcedAlignmentRequest) -> ForcedAlignmentResult:
        return ForcedAlignmentResult(
            status=ForcedAlignmentStatus.UNCONFIGURED,
            provider=self.name,
            error_code=ForcedAlignmentErrorCode.MODEL_UNAVAILABLE,
            error_detail=f"provider {self.name!r} 未配置真实对齐模型",
        )

    def health_check(self) -> ForcedAlignmentResult:
        return ForcedAlignmentResult(
            status=ForcedAlignmentStatus.UNCONFIGURED,
            error_code=ForcedAlignmentErrorCode.MODEL_UNAVAILABLE,
        )


class FakeForcedAlignmentProvider:
    """确定性 Fake：按 token 长度在 [start,end] 内均分。

    - 中文按字符 token（空白不算）；英文按 whitespace 词 token。
    - 每 word confidence 固定 0.5——**不假装高置信**；上层若要 karaoke 应过滤后使用（§5.2）。
    - deep-copy 出输入不影响；无内部状态。
    - `end_ms < start_ms` → FAILED（诚实）；文本为空 → words=[] + OK。
    """

    def __init__(self, *, name: str = "align.fake", execution_location: str = "local") -> None:
        self.name = name
        self.execution_location = execution_location

    def align(self, request: ForcedAlignmentRequest) -> ForcedAlignmentResult:
        req = deepcopy(request)
        if req.end_ms < req.start_ms:
            return ForcedAlignmentResult(
                status=ForcedAlignmentStatus.FAILED,
                provider=self.name,
                error_code=ForcedAlignmentErrorCode.UNKNOWN,
                error_detail=f"end_ms({req.end_ms}) < start_ms({req.start_ms})",
            )
        tokens = self._tokenize(req.text, req.language)
        if not tokens:
            return ForcedAlignmentResult(
                status=ForcedAlignmentStatus.OK,
                provider=self.name,
                words=[],
            )
        total_units = sum(max(1, len(t)) for t in tokens)
        span = req.end_ms - req.start_ms
        words: list[SubtitleWord] = []
        cursor = req.start_ms
        acc = 0
        for i, t in enumerate(tokens):
            share = max(1, len(t))
            acc += share
            if i == len(tokens) - 1:
                end = req.end_ms
            else:
                end = req.start_ms + int(round(span * acc / total_units))
                if end <= cursor:
                    end = cursor + 1
            words.append(SubtitleWord(text=t, start_ms=cursor, end_ms=end, confidence=0.5))
            cursor = end
        return ForcedAlignmentResult(
            status=ForcedAlignmentStatus.OK,
            provider=self.name,
            words=words,
        )

    def health_check(self) -> ForcedAlignmentResult:
        return ForcedAlignmentResult(status=ForcedAlignmentStatus.OK)

    @staticmethod
    def _tokenize(text: str, language: str) -> list[str]:
        if not text.strip():
            return []
        if language.lower().startswith("zh"):
            return [c for c in text if not c.isspace()]
        return _EN_TOKEN_RE.findall(text)


__all__ = [
    "FakeForcedAlignmentProvider",
    "ForcedAlignmentErrorCode",
    "ForcedAlignmentProvider",
    "ForcedAlignmentRequest",
    "ForcedAlignmentResult",
    "ForcedAlignmentStatus",
    "UnconfiguredForcedAlignmentProvider",
]
