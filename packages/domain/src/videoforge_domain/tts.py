"""TTS 合成计划 + Voice Profile 授权护栏 + 时长拟合评估（docs/modules/43 §7-§8）。纯函数。

- `plan_tts_synthesis(sentences, voice_by_speaker, ...)` → list[TTSSynthesisJob]（含 text_hash）
- `validate_voice_profile(profile)` → typed issue（授权状态 + consent + expiration + kind）
- `validate_tts_manifest(manifest, request_text?, target_duration_ms?)` → typed issue
- `text_hash_of(text, language, voice_profile_id, style, target_duration_ms?, lexicon_id?, seed?)`
  → canonical sha256（VF-201 activity_cache_key 精神；同输入永远同 hash）
- `suggest_speed(estimated_ms, target_ms, natural_bounds)` → 语速倍数（§8 建议 0.92-1.08）

**红线**：`license_status != AUTHORIZED` 绝不给出可合成的 job；VoiceProfile 校验独立
（供 UI/persistence 消费），provider 层也应双检——不信任 domain 单点。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    TTSManifest,
    TTSProviderTier,
    VoiceKind,
    VoiceLicenseStatus,
    VoiceProfile,
    VoiceStyle,
)

# §8：TTS 语速自然区间上下限（模板可覆盖，此为默认）
NATURAL_SPEED_MIN = 0.92
NATURAL_SPEED_MAX = 1.08

# TTS 时长评估容差（相对 target 的比例）
_DEFAULT_DURATION_TOLERANCE = 0.10  # ±10%


class VoiceProfileIssueKind(StrEnum):
    LICENSE_NOT_AUTHORIZED = "LICENSE_NOT_AUTHORIZED"
    LICENSE_EXPIRED = "LICENSE_EXPIRED"
    CLONED_MISSING_SAMPLE = "CLONED_MISSING_SAMPLE"  # 合同已拦，双保险
    CLONED_MISSING_CONSENT = "CLONED_MISSING_CONSENT"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"  # 请求语言 vs profile.language


class TTSManifestIssueKind(StrEnum):
    AUDIO_MISSING = "AUDIO_MISSING"  # audio_artifact_id 为 None 但 duration_ms/words 非空
    WORD_TIMINGS_EMPTY = "WORD_TIMINGS_EMPTY"
    WORD_TIMINGS_NOT_MONOTONIC = "WORD_TIMINGS_NOT_MONOTONIC"
    WORD_TIMING_OUT_OF_TOTAL = "WORD_TIMING_OUT_OF_TOTAL"  # word 超出 duration_ms
    TEXT_HASH_MISMATCH = "TEXT_HASH_MISMATCH"  # 提供了 request text 但 hash 对不上
    DURATION_OUT_OF_TOLERANCE = "DURATION_OUT_OF_TOLERANCE"  # 相对 target 超 ±10%
    SPEED_OUT_OF_NATURAL_BOUNDS = "SPEED_OUT_OF_NATURAL_BOUNDS"  # 语速超 §8 区间


@dataclass(frozen=True)
class VoiceProfileIssue:
    kind: VoiceProfileIssueKind
    ref: str
    detail: str


@dataclass(frozen=True)
class TTSManifestIssue:
    kind: TTSManifestIssueKind
    ref: str
    detail: str


@dataclass(frozen=True)
class TTSSynthesisJob:
    """一次待合成的作业（domain 侧计划，非合同持久化——由 workflow/provider 消费）。"""

    sentence_id: str
    text: str
    language: str
    voice_profile_id: str
    provider_tier: TTSProviderTier
    text_hash: str
    style: VoiceStyle | None = None
    target_duration_ms: int | None = None
    lexicon_id: str | None = None
    seed: int | None = None
    suggested_speed: float | None = None
    review_reasons: list[str] = field(default_factory=list)


def text_hash_of(
    text: str,
    *,
    language: str,
    voice_profile_id: str,
    style: VoiceStyle | None = None,
    target_duration_ms: int | None = None,
    lexicon_id: str | None = None,
    seed: int | None = None,
) -> str:
    """规范化 hash（同 41 §11 activity cache key 精神）。同输入永远同哈希——可用作 TTS
    结果缓存键。style/lexicon/seed 参与哈希：改这三者任一即视为新合成。"""
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


def _is_authorized(profile: VoiceProfile, now: datetime | None = None) -> bool:
    """有效授权 = license_status == AUTHORIZED 且未过期。now 为空不做时间判断。"""
    if profile.license_status is not VoiceLicenseStatus.AUTHORIZED:
        return False
    if profile.expires_at is not None and now is not None and profile.expires_at < now:
        return False
    return True


def validate_voice_profile(
    profile: VoiceProfile,
    *,
    now: datetime | None = None,
    request_language: str | None = None,
) -> list[VoiceProfileIssue]:
    """VoiceProfile 护栏；返回全部违规（空 = 通过）。"""
    issues: list[VoiceProfileIssue] = []
    if profile.license_status is not VoiceLicenseStatus.AUTHORIZED:
        issues.append(
            VoiceProfileIssue(
                VoiceProfileIssueKind.LICENSE_NOT_AUTHORIZED,
                profile.id,
                f"license_status={profile.license_status.value} 不可合成"
                "（仅 AUTHORIZED 可用，§7 硬红线）",
            )
        )
    if profile.expires_at is not None and now is not None and profile.expires_at < now:
        issues.append(
            VoiceProfileIssue(
                VoiceProfileIssueKind.LICENSE_EXPIRED,
                profile.id,
                f"license expired at {profile.expires_at.isoformat()}",
            )
        )
    # 合同层已拦但仍双保险（防手工构造/未来路径）
    if profile.voice_kind is VoiceKind.CLONED:
        if not profile.sample_source_ref:
            issues.append(
                VoiceProfileIssue(
                    VoiceProfileIssueKind.CLONED_MISSING_SAMPLE,
                    profile.id,
                    "CLONED 缺 sample_source_ref",
                )
            )
        if not profile.consent_ref:
            issues.append(
                VoiceProfileIssue(
                    VoiceProfileIssueKind.CLONED_MISSING_CONSENT,
                    profile.id,
                    "CLONED 缺 consent_ref",
                )
            )
    if request_language is not None and request_language != profile.language:
        issues.append(
            VoiceProfileIssue(
                VoiceProfileIssueKind.LANGUAGE_MISMATCH,
                profile.id,
                f"请求语言 {request_language} 与 profile.language={profile.language} 不一致",
            )
        )
    return issues


def is_authorized_for_synthesis(
    profile: VoiceProfile,
    *,
    now: datetime | None = None,
) -> bool:
    """便捷入口——只检授权，用于路由/合成前的 gate。"""
    return _is_authorized(profile, now)


def suggest_speed(
    estimated_ms: int,
    target_ms: int,
    *,
    natural_min: float = NATURAL_SPEED_MIN,
    natural_max: float = NATURAL_SPEED_MAX,
) -> float:
    """按 §8 时长拟合：`speed = estimated / target`（合成后应总时长 ≈ target）。

    结果**不自动 clip**——超区间由上层护栏（validate_tts_manifest 或 workflow）报告
    需按 §8 顺序回退（1. LLM 改写 / 2. TTS 语速微调 / 3. Hold / 4. 伸缩 / 5. 重排）。
    """
    if target_ms <= 0:
        return 1.0
    return round(estimated_ms / target_ms, 4)


def plan_tts_synthesis(
    sentences: list[tuple[str, str, str]],  # [(sentence_id, text, language)]
    *,
    voice_by_speaker: Mapping[str, VoiceProfile],
    default_voice: VoiceProfile,
    speaker_by_sentence: Mapping[str, str] | None = None,
    style_by_sentence: Mapping[str, VoiceStyle] | None = None,
    target_duration_by_sentence: Mapping[str, int] | None = None,
    estimated_duration_by_sentence: Mapping[str, int] | None = None,
    lexicon_id: str | None = None,
    seed: int | None = None,
    now: datetime | None = None,
) -> list[TTSSynthesisJob]:
    """把一批句子 → TTSSynthesisJob 列表。

    - `voice_by_speaker`：speaker_id → VoiceProfile 映射；缺 speaker 或无映射用
      `default_voice`。
    - **未授权 profile** 会被跳过（不生成 job）；调用方从"缺失 job"里能看出漏了哪些句子，
      配合 validate_voice_profile 提示。
    - 语速建议基于 estimated / target，超 §8 自然区间即 review_reasons 加提示。
    """
    speakers = speaker_by_sentence or {}
    styles = style_by_sentence or {}
    targets = target_duration_by_sentence or {}
    estimates = estimated_duration_by_sentence or {}
    jobs: list[TTSSynthesisJob] = []
    for sid, text, lang in sentences:
        speaker = speakers.get(sid)
        voice = voice_by_speaker.get(speaker) if speaker else None
        voice = voice or default_voice
        if not is_authorized_for_synthesis(voice, now=now):
            continue  # 明示跳过；VF-407 review 会看到缺失
        style = styles.get(sid)
        target = targets.get(sid)
        est = estimates.get(sid)
        suggested = None
        reasons: list[str] = []
        if target and est:
            suggested = suggest_speed(est, target)
            if suggested < NATURAL_SPEED_MIN or suggested > NATURAL_SPEED_MAX:
                reasons.append(TTSManifestIssueKind.SPEED_OUT_OF_NATURAL_BOUNDS.value)
        jobs.append(
            TTSSynthesisJob(
                sentence_id=sid,
                text=text,
                language=lang,
                voice_profile_id=voice.id,
                provider_tier=voice.provider_tier,
                text_hash=text_hash_of(
                    text,
                    language=lang,
                    voice_profile_id=voice.id,
                    style=style,
                    target_duration_ms=target,
                    lexicon_id=lexicon_id,
                    seed=seed,
                ),
                style=style,
                target_duration_ms=target,
                lexicon_id=lexicon_id,
                seed=seed,
                suggested_speed=suggested,
                review_reasons=reasons,
            )
        )
    return jobs


def validate_tts_manifest(
    manifest: TTSManifest,
    *,
    request_text: str | None = None,
    request_style: VoiceStyle | None = None,
    request_lexicon_id: str | None = None,
    target_duration_ms: int | None = None,
    duration_tolerance: float = _DEFAULT_DURATION_TOLERANCE,
    natural_min: float = NATURAL_SPEED_MIN,
    natural_max: float = NATURAL_SPEED_MAX,
) -> list[TTSManifestIssue]:
    """TTS 合成结果护栏；返回全部违规（空 = 通过）。"""
    issues: list[TTSManifestIssue] = []
    if manifest.audio_artifact_id is None and (manifest.duration_ms or manifest.word_timings):
        issues.append(
            TTSManifestIssue(
                TTSManifestIssueKind.AUDIO_MISSING,
                manifest.id,
                "audio_artifact_id 为 None 但 duration/word_timings 非空",
            )
        )
    if manifest.audio_artifact_id is not None:
        if not manifest.word_timings:
            issues.append(
                TTSManifestIssue(
                    TTSManifestIssueKind.WORD_TIMINGS_EMPTY,
                    manifest.id,
                    "audio 已产但 word_timings 为空——subtitle 对齐将失败",
                )
            )
        else:
            # 单调
            prev_end = -1
            for w in manifest.word_timings:
                if w.start_ms < prev_end:
                    issues.append(
                        TTSManifestIssue(
                            TTSManifestIssueKind.WORD_TIMINGS_NOT_MONOTONIC,
                            manifest.id,
                            f"word {w.text!r} start={w.start_ms} 早于前一 end={prev_end}",
                        )
                    )
                    break
                prev_end = w.end_ms
            # 词超总时长
            if manifest.duration_ms is not None:
                last_end = max(w.end_ms for w in manifest.word_timings)
                if last_end > manifest.duration_ms:
                    issues.append(
                        TTSManifestIssue(
                            TTSManifestIssueKind.WORD_TIMING_OUT_OF_TOTAL,
                            manifest.id,
                            f"末 word end={last_end}ms > duration={manifest.duration_ms}ms",
                        )
                    )
    # text_hash 校验（若 caller 提供 request 上下文）
    if request_text is not None:
        expected = text_hash_of(
            request_text,
            language=manifest.language,
            voice_profile_id=manifest.voice_profile_id,
            style=request_style,
            target_duration_ms=target_duration_ms,
            lexicon_id=request_lexicon_id,
            seed=manifest.seed,
        )
        if expected != manifest.text_hash:
            issues.append(
                TTSManifestIssue(
                    TTSManifestIssueKind.TEXT_HASH_MISMATCH,
                    manifest.id,
                    "manifest.text_hash 与 request 派生的 hash 不一致",
                )
            )
    # 时长偏差
    if (
        target_duration_ms is not None
        and target_duration_ms > 0
        and manifest.duration_ms is not None
    ):
        ratio = manifest.duration_ms / target_duration_ms
        if ratio < 1 - duration_tolerance or ratio > 1 + duration_tolerance:
            issues.append(
                TTSManifestIssue(
                    TTSManifestIssueKind.DURATION_OUT_OF_TOLERANCE,
                    manifest.id,
                    f"duration {manifest.duration_ms}ms 相对目标 {target_duration_ms}ms "
                    f"偏差 {(ratio - 1):+.0%} 超容差 ±{int(duration_tolerance * 100)}%",
                )
            )
    # 语速自然区间
    if manifest.speed_used is not None and (
        manifest.speed_used < natural_min or manifest.speed_used > natural_max
    ):
        issues.append(
            TTSManifestIssue(
                TTSManifestIssueKind.SPEED_OUT_OF_NATURAL_BOUNDS,
                manifest.id,
                f"speed_used={manifest.speed_used:.2f} 超自然区间"
                f"[{natural_min:.2f}, {natural_max:.2f}]（§8 应先走 LLM 改写等回退）",
            )
        )
    return issues


def is_valid_voice_profile(
    profile: VoiceProfile,
    *,
    now: datetime | None = None,
    request_language: str | None = None,
) -> bool:
    return not validate_voice_profile(
        profile,
        now=now,
        request_language=request_language,
    )


def is_valid_tts_manifest(
    manifest: TTSManifest,
    *,
    request_text: str | None = None,
    request_style: VoiceStyle | None = None,
    request_lexicon_id: str | None = None,
    target_duration_ms: int | None = None,
) -> bool:
    return not validate_tts_manifest(
        manifest,
        request_text=request_text,
        request_style=request_style,
        request_lexicon_id=request_lexicon_id,
        target_duration_ms=target_duration_ms,
    )
