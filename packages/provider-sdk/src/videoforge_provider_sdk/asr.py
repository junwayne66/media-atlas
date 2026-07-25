"""ASR 端口 + Fake/路由（docs/modules/41 §7）。

ASR Provider 实现本协议，只进出统一 Transcript 合同——业务不依赖任何 ASR 引擎内部。
真实引擎（whisper.cpp / WhisperX / FunASR）需模型，属停止条件延后：默认 UnconfiguredASRProvider
诚实返回 UNCONFIGURED，不静默假装转写；FakeASRProvider 回放录制转录，供下游开发。

路由（41 §7.1）：按语言 + 执行策略（本地快速稿 vs 云精确词级）+ 是否需热词（中文热点词走
支持热词的 Provider）择优，失败回退。细粒度低置信标记是 domain 的后处理 pass（本层不依赖
domain），Provider 只做粗粒度 NEEDS_REVIEW 判定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from videoforge_contracts import Transcript


class ASRStatus(StrEnum):
    OK = "ok"  # 转写完成，置信度可接受
    NEEDS_REVIEW = "needs_review"  # 转写完成但整体低置信 → 转人工审核（ASR_LOW_CONFIDENCE）
    FAILED = "failed"  # 转写/对齐失败
    UNCONFIGURED = "unconfigured"  # 真实引擎未接入（需模型，停止条件）
    UNSUPPORTED_LANGUAGE = "unsupported_language"  # Provider 不支持该语言


class ASRErrorCode(StrEnum):
    """获取层 §12 的 ASR 相关码 + 运行期分类。"""

    LOW_CONFIDENCE = "ASR_LOW_CONFIDENCE"
    ALIGNMENT_FAILED = "ALIGNMENT_FAILED"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    UNCONFIGURED = "UNCONFIGURED"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class ASRRequest:
    audio_path: Path
    language_hint: str | None = None  # None → 自动/默认；混语见 LanguageSegmenter
    hotwords: tuple[str, ...] = ()  # 中文热点词（产品名/人名）偏置
    policy: str = "local_preferred"  # local_preferred / cloud_preferred


@dataclass
class ASRResult:
    status: ASRStatus
    provider: str
    transcript: Transcript | None = None
    error_code: ASRErrorCode | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in (ASRStatus.OK, ASRStatus.NEEDS_REVIEW)


@runtime_checkable
class ASRProvider(Protocol):
    name: str
    languages: tuple[str, ...]  # 支持的 BCP-47 语言
    execution_location: str  # local / cloud
    supports_hotwords: bool

    def transcribe(self, request: ASRRequest) -> ASRResult: ...

    def health_check(self) -> ASRResult: ...


class UnconfiguredASRProvider:
    """默认：真实引擎未接入（需模型）。返回 UNCONFIGURED，不静默假装转写。"""

    supports_hotwords = False

    def __init__(
        self,
        name: str = "asr.unconfigured",
        *,
        languages: tuple[str, ...] = ("zh-CN", "en-US"),
        execution_location: str = "local",
    ) -> None:
        self.name = name
        self.languages = languages
        self.execution_location = execution_location

    def transcribe(self, request: ASRRequest) -> ASRResult:
        return ASRResult(
            status=ASRStatus.UNCONFIGURED,
            provider=self.name,
            error_code=ASRErrorCode.UNCONFIGURED,
            detail="ASR 引擎未接入（需模型/授权）；请用手工转录或稍后重试",
        )

    def health_check(self) -> ASRResult:
        return self.transcribe(ASRRequest(audio_path=Path("/dev/null")))


def _min_segment_confidence(transcript: Transcript) -> float:
    return min((s.confidence for s in transcript.segments), default=1.0)


class FakeASRProvider:
    """回放录制转录（按语言选）；注入热词（记录 + 偏置匹配词置信度）。全程不触模型。"""

    def __init__(
        self,
        *,
        name: str,
        languages: tuple[str, ...],
        execution_location: str = "local",
        supports_hotwords: bool = False,
        transcripts: dict[str, Transcript],
        review_floor: float = 0.7,
    ) -> None:
        self.name = name
        self.languages = languages
        self.execution_location = execution_location
        self.supports_hotwords = supports_hotwords
        self._transcripts = dict(transcripts)
        self._review_floor = review_floor

    def _apply_hotwords(self, base: Transcript, hotwords: tuple[str, ...]) -> Transcript:
        if not self.supports_hotwords:
            # 不支持热词的 Provider 既不偏置、也不虚报注入（hotwords 只记真正用上的）
            return base
        hot = set(hotwords)
        new_segments = []
        for seg in base.segments:
            new_words = [
                w.model_copy(update={"confidence": max(w.confidence, 0.98)}) if w.text in hot else w
                for w in seg.words
            ]
            new_segments.append(seg.model_copy(update={"words": new_words}))
        return base.model_copy(update={"segments": new_segments, "hotwords": list(hotwords)})

    def transcribe(self, request: ASRRequest) -> ASRResult:
        lang = request.language_hint or self.languages[0]
        if lang not in self.languages:
            return ASRResult(
                status=ASRStatus.UNSUPPORTED_LANGUAGE,
                provider=self.name,
                error_code=ASRErrorCode.UNSUPPORTED_LANGUAGE,
                detail=f"{self.name} 不支持语言 {lang}",
            )
        base = self._transcripts.get(lang)
        if base is None:
            # 声明支持但无该语言录制 → 诚实 FAILED，绝不回放别的语言冒充
            return ASRResult(
                status=ASRStatus.FAILED,
                provider=self.name,
                error_code=ASRErrorCode.RESULT_UNKNOWN,
                detail=f"无 {lang} 的录制转录",
            )
        transcript = self._apply_hotwords(base, request.hotwords)
        if _min_segment_confidence(transcript) < self._review_floor:
            return ASRResult(
                status=ASRStatus.NEEDS_REVIEW,
                provider=self.name,
                transcript=transcript,
                error_code=ASRErrorCode.LOW_CONFIDENCE,
                detail="整体置信度偏低，建议人工审核",
            )
        return ASRResult(status=ASRStatus.OK, provider=self.name, transcript=transcript)

    def health_check(self) -> ASRResult:
        return ASRResult(status=ASRStatus.OK, provider=self.name)


@dataclass(frozen=True)
class ASRAttempt:
    provider: str
    status: ASRStatus


@dataclass
class ASRRouteResult:
    result: ASRResult
    attempts: list[ASRAttempt] = field(default_factory=list)
    chain: list[str] = field(default_factory=list)  # 实际候选顺序（可解释）

    @property
    def ok(self) -> bool:
        return self.result.ok


# 命中即终止（不再回退）：转写成功/需审核（已产出）。UNCONFIGURED/FAILED 才回退下一个。
_ASR_TERMINAL = frozenset({ASRStatus.OK, ASRStatus.NEEDS_REVIEW})


class ASRRouter:
    """按语言 + 策略 + 热词择优，失败回退（41 §7.1）。"""

    def __init__(self, providers: list[ASRProvider]) -> None:
        self._providers = list(providers)

    def candidates(self, request: ASRRequest) -> list[ASRProvider]:
        lang = request.language_hint
        # 支持该语言的 Provider（无 language_hint 则全部候选）
        pool = [p for p in self._providers if lang is None or lang in p.languages]
        want_hotwords = bool(request.hotwords)
        preferred_loc = "cloud" if request.policy == "cloud_preferred" else "local"

        def key(p: ASRProvider) -> tuple[int, int, str]:
            # 需热词时支持热词的排前；再按策略本地/云优先；最后按名字稳定
            hot_rank = 0 if (want_hotwords and p.supports_hotwords) else 1
            loc_rank = 0 if p.execution_location == preferred_loc else 1
            return (hot_rank, loc_rank, p.name)

        return sorted(pool, key=key)

    def transcribe(self, request: ASRRequest) -> ASRRouteResult:
        chain = self.candidates(request)
        attempts: list[ASRAttempt] = []
        last: ASRResult | None = None
        for provider in chain:
            res = provider.transcribe(request)
            attempts.append(ASRAttempt(provider.name, res.status))
            last = res
            if res.status in _ASR_TERMINAL:
                return ASRRouteResult(res, attempts, [p.name for p in chain])
        result = last or ASRResult(
            status=ASRStatus.UNCONFIGURED,
            provider="asr.router",
            error_code=ASRErrorCode.UNCONFIGURED,
            detail="无可用 ASR Provider（全部未配置）；请手工转录",
        )
        return ASRRouteResult(result, attempts, [p.name for p in chain])


# —— 混语预分段（41 §7.1「先做语言片段检测」）——


@dataclass(frozen=True)
class LanguageSpan:
    start_ms: int
    end_ms: int
    language: str


class LanguageSegmenter(Protocol):
    def segment(self, audio_path: Path) -> list[LanguageSpan]: ...


class FakeLanguageSegmenter:
    """回放录制语言片段（供混语流程开发）。"""

    def __init__(self, spans: list[LanguageSpan]) -> None:
        self._spans = list(spans)

    def segment(self, audio_path: Path) -> list[LanguageSpan]:
        return list(self._spans)


class UnconfiguredLanguageSegmenter:
    """默认：语言分段检测未接入（需模型）——返回空，交由单语言路径 + 人工。"""

    def segment(self, audio_path: Path) -> list[LanguageSpan]:
        return []
