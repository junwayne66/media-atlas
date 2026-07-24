"""音频合成合同（docs/modules/43 §9）。

- 分轨：ORIGINAL_VOICE / VOICE_DUB / MUSIC / SFX / AMBIENCE
- Ducking：以**语音活动**为 sidechain（不是"每切点泵动"）
- 响度：LoudnessTarget lufs + true_peak；**True Peak Gate 必须通过**（QA 层已有 TRUE_PEAK_CLIP
  BLOCKER，此处提前设 target 让 provider 满足）
- Room Tone：可选背景噪，配音段之间避免"绝对静音"
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel


class AudioMixTrackKind(StrEnum):
    """分轨类型（§9 分轨设计）。"""

    ORIGINAL_VOICE = "ORIGINAL_VOICE"  # 原始人声（可能被 Ducking 或降低）
    VOICE_DUB = "VOICE_DUB"  # 目标语言配音（TTS 或人配）
    MUSIC = "MUSIC"
    SFX = "SFX"
    AMBIENCE = "AMBIENCE"  # 环境声/Room Tone


class DuckingSidechain(StrEnum):
    """Ducking sidechain 触发源。"""

    VOICE_ACTIVITY = "VOICE_ACTIVITY"  # 语音活动（§9 首选）
    CUT_POINT = "CUT_POINT"  # 切点（§9 警告：会泵动，仅作对比使用）
    NONE = "NONE"


class DuckingPolicy(ContractModel):
    """Ducking 参数（单位与 ffmpeg sidechaincompress 兼容）。"""

    sidechain: DuckingSidechain
    threshold_db: float = Field(default=-20.0, le=0.0, description="触发阈值（dB）")
    ratio: float = Field(default=8.0, ge=1.0, description="压缩比 ≥ 1")
    attack_ms: int = Field(default=20, ge=0)
    release_ms: int = Field(default=300, ge=0)
    reduction_db: float = Field(
        default=-8.0, le=0.0, description="被压轨下探目标（-8dB 常见）",
    )


class AudioMixTrack(ContractModel):
    """一条参与合成的音轨。"""

    id: str = Field(min_length=1)
    kind: AudioMixTrackKind
    source_artifact_id: str | None = Field(
        default=None, description="音频 artifact；VOICE_DUB 常来自 TTSManifest",
    )
    tts_manifest_id: str | None = Field(
        default=None, description="VOICE_DUB 关联 TTS Manifest（可选）",
    )
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    gain_db: float = Field(default=0.0)
    ducked_by: str | None = Field(
        default=None,
        description="被哪条轨 Ducking 的 track id；一般 MUSIC/AMBIENCE 被 VOICE_* 压",
    )

    @model_validator(mode="after")
    def _check_span(self) -> "AudioMixTrack":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        return self


class LoudnessTarget(ContractModel):
    """响度目标（§9 平台/模板配置）。True Peak Gate = 硬顶（QA BLOCKER 已定义）。"""

    lufs: float = Field(default=-14.0, description="整体积分响度目标（LUFS）")
    lufs_tolerance: float = Field(default=2.0, ge=0.0, description="±LUFS 容差")
    true_peak_max_dbtp: float = Field(
        default=-1.0, le=0.0,
        description="True Peak 硬顶（dBTP）；QA TRUE_PEAK_CLIP 触发 BLOCKER",
    )

    @model_validator(mode="after")
    def _check_true_peak(self) -> "LoudnessTarget":
        # QA VF-309 TRUE_PEAK_CLIP 硬顶通常为 -1 dBTP；允许更严但不允许更宽
        if self.true_peak_max_dbtp > 0.0:
            raise ValueError("true_peak_max_dbtp 必须 ≤ 0（dBTP 硬顶不能为正）")
        return self


class AudioMixPlan(ContractModel):
    """一次音频合成计划。tracks + ducking + loudness_target + room_tone。"""

    id: str = Field(min_length=1)
    tracks: list[AudioMixTrack] = Field(default_factory=list)
    ducking: DuckingPolicy | None = None
    loudness_target: LoudnessTarget
    room_tone_artifact_id: str | None = Field(
        default=None, description="配音段间的背景噪；空则允许绝对静音",
    )
    total_duration_ms: int = Field(gt=0)
    created_at: datetime

    @model_validator(mode="after")
    def _check_refs(self) -> "AudioMixPlan":
        ids = {t.id for t in self.tracks}
        if len(ids) != len(self.tracks):
            raise ValueError("tracks 内 id 重复")
        for t in self.tracks:
            if t.ducked_by and t.ducked_by not in ids:
                raise ValueError(
                    f"track {t.id!r} ducked_by {t.ducked_by!r} 不在 tracks 内"
                )
            if t.ducked_by == t.id:
                raise ValueError(f"track {t.id!r} 不能被自己 Ducking")
        return self
