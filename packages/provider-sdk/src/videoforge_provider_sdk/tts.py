"""TTS 合成端口 + Fake + Router（docs/modules/43 §7）。

`synthesize(text, language, voice_profile, style, target_duration_ms, lexicon, seed)`
→ AudioArtifact + WordTimings。

**红线**（§7 硬要求，与合同层双保险）：`voice_profile.license_status != AUTHORIZED`
Provider 层再检一次——即使 domain 层放行了（bug/绕过路径），FakeTTSProvider 也拒。
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import (
    PronunciationLexicon,
    TTSManifest,
    TTSProviderTier,
    TTSWordTiming,
    VoiceLicenseStatus,
    VoiceProfile,
    VoiceStyle,
)

_EN_TOKEN_RE = re.compile(r"\S+")


class TTSStatus(StrEnum):
    OK = "OK"
    FAILED = "FAILED"
    UNCONFIGURED = "UNCONFIGURED"
    VOICE_UNAUTHORIZED = "VOICE_UNAUTHORIZED"  # 授权红线拒
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"


class TTSErrorCode(StrEnum):
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    VOICE_UNAUTHORIZED = "VOICE_UNAUTHORIZED"
    VOICE_EXPIRED = "VOICE_EXPIRED"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    RATE_LIMITED = "RATE_LIMITED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TTSRequest:
    """一次 TTS 合成请求。"""

    sentence_id: str
    text: str
    language: str
    voice_profile: VoiceProfile
    style: VoiceStyle | None = None
    target_duration_ms: int | None = None
    lexicon: PronunciationLexicon | None = None
    seed: int | None = None


@dataclass(frozen=True)
class TTSResult:
    status: TTSStatus
    manifest: TTSManifest | None = None
    error_code: TTSErrorCode | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class TTSProvider(Protocol):
    """统一 TTS 端口（§7）。"""

    name: str
    execution_location: str  # local / cloud
    tier: TTSProviderTier

    def synthesize(self, request: TTSRequest) -> TTSResult: ...

    def health_check(self) -> TTSResult: ...


class UnconfiguredTTSProvider:
    """诚实占位：无真实 TTS 引擎，绝不合成。"""

    def __init__(
        self,
        *,
        name: str = "tts.unconfigured",
        tier: TTSProviderTier = TTSProviderTier.CLOUD_HIGH_QUALITY,
        execution_location: str = "cloud",
    ) -> None:
        self.name = name
        self.tier = tier
        self.execution_location = execution_location

    def synthesize(self, request: TTSRequest) -> TTSResult:
        return TTSResult(
            status=TTSStatus.UNCONFIGURED,
            error_code=TTSErrorCode.ENGINE_UNAVAILABLE,
            error_detail=(f"provider {self.name!r} 未配置真实 TTS 引擎（{self.tier.value}）"),
        )

    def health_check(self) -> TTSResult:
        return TTSResult(
            status=TTSStatus.UNCONFIGURED,
            error_code=TTSErrorCode.ENGINE_UNAVAILABLE,
        )


def _text_hash_local(
    text: str,
    language: str,
    voice_profile_id: str,
    style: VoiceStyle | None,
    target_duration_ms: int | None,
    lexicon_id: str | None,
    seed: int | None,
) -> str:
    """provider 侧算 text_hash——与 domain.text_hash_of 逐位一致（不能 import domain）。"""
    payload: dict[str, object] = {
        "text": text,
        "language": language,
        "voice_profile_id": voice_profile_id,
        "target_duration_ms": target_duration_ms,
        "lexicon_id": lexicon_id,
        "seed": seed,
    }
    if style is not None:
        payload["style"] = {
            "pace": style.pace,
            "emotion": style.emotion,
            "energy": style.energy,
            "pitch_semitones": style.pitch_semitones,
        }
    else:
        payload["style"] = None
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FakeTTSProvider:
    """确定性 Fake：按语速估算 duration + 均分 WordTiming；输出 dummy artifact id。

    - **VOICE_UNAUTHORIZED 硬拦**：`voice_profile.license_status != AUTHORIZED`
      立即返 VOICE_UNAUTHORIZED（§7 红线；即便 domain 层放行也不合成）。
    - `style.pace` 参与 duration 计算（模拟 §8 语速微调）。
    - 每 word confidence 固定 0.5（不假装高置信）。
    - deep-copy 输入避免污染；无内部状态。
    - 无真实音频/字节；warnings 明示"非真实音频"。
    """

    _CHARS_PER_SEC_ZH = 5.0
    _WORDS_PER_SEC_EN = 2.5

    def __init__(
        self,
        *,
        name: str = "tts.fake.cloud",
        tier: TTSProviderTier = TTSProviderTier.CLOUD_HIGH_QUALITY,
        execution_location: str = "cloud",
        supported_languages: tuple[str, ...] = ("zh-CN", "en-US"),
        tool_version: str = "fake-tts-1.0",
    ) -> None:
        self.name = name
        self.tier = tier
        self.execution_location = execution_location
        self.supported_languages = supported_languages
        self.tool_version = tool_version

    def _tokenize(self, text: str, language: str) -> list[str]:
        if language.lower().startswith("zh"):
            return [c for c in text if not c.isspace()]
        return _EN_TOKEN_RE.findall(text)

    def _estimate_ms(self, text: str, language: str, pace: float | None) -> int:
        speed = pace if (pace and pace > 0) else 1.0
        if language.lower().startswith("zh"):
            units = sum(1 for c in text if not c.isspace())
            rate = self._CHARS_PER_SEC_ZH
        else:
            units = len(_EN_TOKEN_RE.findall(text))
            rate = self._WORDS_PER_SEC_EN
        if units == 0:
            return 0
        # speed>1 → 快 → 时长短
        return int(round(units / (rate * speed) * 1000))

    def synthesize(self, request: TTSRequest) -> TTSResult:
        req = deepcopy(request)
        vp = req.voice_profile
        if vp.license_status is not VoiceLicenseStatus.AUTHORIZED:
            return TTSResult(
                status=TTSStatus.VOICE_UNAUTHORIZED,
                error_code=TTSErrorCode.VOICE_UNAUTHORIZED,
                error_detail=(
                    f"voice_profile {vp.id!r} license_status="
                    f"{vp.license_status.value}，绝不合成（§7 硬红线）"
                ),
            )
        if req.language not in self.supported_languages:
            return TTSResult(
                status=TTSStatus.UNSUPPORTED_LANGUAGE,
                error_code=TTSErrorCode.UNSUPPORTED_LANGUAGE,
                error_detail=f"provider {self.name!r} 未支持语言 {req.language!r}",
            )
        pace = req.style.pace if req.style else None
        duration = self._estimate_ms(req.text, req.language, pace)
        tokens = self._tokenize(req.text, req.language)
        word_timings: list[TTSWordTiming] = []
        if tokens and duration > 0:
            total_units = sum(max(1, len(t)) for t in tokens)
            cursor = 0
            acc = 0
            for i, t in enumerate(tokens):
                share = max(1, len(t))
                acc += share
                if i == len(tokens) - 1:
                    end = duration
                else:
                    end = int(round(duration * acc / total_units))
                    if end <= cursor:
                        end = cursor + 1
                word_timings.append(
                    TTSWordTiming(
                        text=t,
                        start_ms=cursor,
                        end_ms=end,
                        confidence=0.5,
                    )
                )
                cursor = end
        text_hash = _text_hash_local(
            req.text,
            req.language,
            vp.id,
            req.style,
            req.target_duration_ms,
            req.lexicon.id if req.lexicon else None,
            req.seed,
        )
        # 用与 request 完全一致的 datetime；由调用方传 → 此处无 clock 依赖，取一固定伪时间
        from datetime import UTC, datetime

        manifest = TTSManifest(
            id=f"tts-{req.sentence_id}-{text_hash[:12]}",
            sentence_id=req.sentence_id,
            voice_profile_id=vp.id,
            language=req.language,
            text_hash=text_hash,
            provider=self.name,
            provider_tier=self.tier,
            tool_version=self.tool_version,
            audio_artifact_id=f"fake-tts-{req.sentence_id}",
            duration_ms=duration,
            word_timings=word_timings,
            speed_used=pace or 1.0,
            seed=req.seed,
            created_at=datetime(2026, 7, 24, tzinfo=UTC),  # 确定性
        )
        return TTSResult(
            status=TTSStatus.OK,
            manifest=manifest,
            warnings=["Fake TTS：非真实音频，仅供 pipeline 开发"],
        )

    def health_check(self) -> TTSResult:
        return TTSResult(status=TTSStatus.OK)


class TTSRouter:
    """按 provider tier 优先级路由 + fallback。默认 CLOUD_HIGH_QUALITY → SELF_HOSTED →
    SYSTEM_PREVIEW（§7）。VOICE_UNAUTHORIZED / UNSUPPORTED_LANGUAGE 是**终局**——不 fallback
    到别的 provider（品牌一致性 + 安全一致性）；UNCONFIGURED / FAILED 才 fallback 到下一
    tier。"""

    DEFAULT_ORDER: tuple[TTSProviderTier, ...] = (
        TTSProviderTier.CLOUD_HIGH_QUALITY,
        TTSProviderTier.SELF_HOSTED,
        TTSProviderTier.SYSTEM_PREVIEW,
    )

    _TERMINAL_STATUSES: frozenset[TTSStatus] = frozenset(
        {
            TTSStatus.OK,
            TTSStatus.VOICE_UNAUTHORIZED,
            TTSStatus.UNSUPPORTED_LANGUAGE,
        }
    )

    def __init__(
        self,
        providers: dict[TTSProviderTier, TTSProvider],
        *,
        order: tuple[TTSProviderTier, ...] | None = None,
    ) -> None:
        self.providers = providers
        self.order = order or self.DEFAULT_ORDER

    def synthesize(self, request: TTSRequest) -> TTSResult:
        attempts: list[str] = []
        last: TTSResult | None = None
        for tier in self.order:
            provider = self.providers.get(tier)
            if provider is None:
                continue
            result = provider.synthesize(request)
            attempts.append(f"{tier.value}:{result.status.value}")
            if result.status in self._TERMINAL_STATUSES:
                # 附上 attempts 供上层排错
                merged_warnings = list(result.warnings) + [
                    f"router attempts: {' → '.join(attempts)}"
                ]
                return TTSResult(
                    status=result.status,
                    manifest=result.manifest,
                    error_code=result.error_code,
                    error_detail=result.error_detail,
                    warnings=merged_warnings,
                )
            last = result
        # 全部失败
        detail = f"router 用尽所有 tier；attempts: {' → '.join(attempts)}"
        return TTSResult(
            status=TTSStatus.FAILED,
            error_code=(last.error_code if last else TTSErrorCode.ENGINE_UNAVAILABLE),
            error_detail=detail,
        )


__all__ = [
    "FakeTTSProvider",
    "TTSErrorCode",
    "TTSProvider",
    "TTSRequest",
    "TTSResult",
    "TTSRouter",
    "TTSStatus",
    "UnconfiguredTTSProvider",
]
