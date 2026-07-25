"""TTS 合同（docs/modules/43 §7）。

`synthesize(text, language, voice_ref, style, target_duration, pronunciation_lexicon, seed)
→ AudioArtifact + WordTimings`。

**红线**（§7）：声音复刻**必须**明确 Voice Profile；每个 Voice Profile 记录样本来源和授权
状态；`license_status != AUTHORIZED` 绝不用于合成——合同层与 provider 层双保险。
`voice_kind=CLONED` 必须携带 `sample_source_ref` + `consent_ref`（sample 与 consent 齐全
才有资格 AUTHORIZED）。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from videoforge_contracts.base import ContractModel


class VoiceKind(StrEnum):
    """声音种类。"""

    CLONED = "CLONED"  # 复刻声（真实人声克隆，最高授权要求）
    PRESET = "PRESET"  # 频道预设（品牌/角色统一声，可复用）
    SYSTEM = "SYSTEM"  # 系统 TTS（macOS SpeechSynthesizer 等，仅预览）


class VoiceLicenseStatus(StrEnum):
    """Voice Profile 授权状态。**只有 AUTHORIZED 可用于合成**。"""

    AUTHORIZED = "AUTHORIZED"
    PENDING = "PENDING"  # 审核中，UI 可显示但不合成
    DENIED = "DENIED"  # 拒授权，永不合成
    UNCONFIRMED = "UNCONFIRMED"  # 未确认（默认新建状态）
    EXPIRED = "EXPIRED"  # 授权过期


class TTSProviderTier(StrEnum):
    """provider 分层（供路由用）。云端最高质，系统最低但预览便宜。"""

    CLOUD_HIGH_QUALITY = "CLOUD_HIGH_QUALITY"
    SELF_HOSTED = "SELF_HOSTED"  # CosyVoice / GPT-SoVITS
    SYSTEM_PREVIEW = "SYSTEM_PREVIEW"  # macOS 系统 TTS 等


class VoiceStyle(ContractModel):
    """合成风格 hints（provider 可用则用，不强制）。"""

    pace: float | None = Field(
        default=None,
        gt=0.0,
        le=3.0,
        description="语速倍数；建议 0.92-1.08（§8 时长拟合）",
    )
    emotion: str | None = Field(
        default=None,
        description="neutral / cheerful / serious / excited 等标签",
    )
    energy: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="能量/音量强度提示",
    )
    pitch_semitones: float | None = Field(
        default=None,
        ge=-12.0,
        le=12.0,
        description="音调偏移（半音）",
    )


class VoiceProfile(ContractModel):
    """一个可复用的声音配置文件。

    `voice_kind=CLONED` 必须有 `sample_source_ref`（原始采样来源引用）+ `consent_ref`
    （说话人同意书引用）；否则合同层拒（§7 硬红线）。`license_status=AUTHORIZED` 是使用
    合成的**必要**条件——合同层与 provider 层双检；expiration 到期后 provider 应刷新到
    EXPIRED（合同层不能自动判断时间）。
    """

    id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    language: str = Field(min_length=1, description="主语言，如 zh-CN；跨语言由 provider 处理")
    voice_kind: VoiceKind
    license_status: VoiceLicenseStatus = VoiceLicenseStatus.UNCONFIRMED
    provider_tier: TTSProviderTier = TTSProviderTier.CLOUD_HIGH_QUALITY
    provider_voice_id: str | None = Field(
        default=None,
        description="provider 侧的具体 voice id（云端/自托管返回值）",
    )
    sample_source_ref: str | None = Field(
        default=None,
        description="原始采样来源引用（artifact id / URL）；CLONED 必填",
    )
    consent_ref: str | None = Field(
        default=None,
        description="说话人授权同意书引用；CLONED 必填",
    )
    expires_at: datetime | None = Field(default=None, description="授权到期时间（可选）")
    notes: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def _check_clone_consent(self) -> "VoiceProfile":
        if self.voice_kind is VoiceKind.CLONED:
            if not self.sample_source_ref:
                raise ValueError("voice_kind=CLONED 必须携带 sample_source_ref（§7 硬红线）")
            if not self.consent_ref:
                raise ValueError("voice_kind=CLONED 必须携带 consent_ref（§7 硬红线）")
        return self


class PronunciationEntry(ContractModel):
    """发音词典的一条：surface（原文形式）→ ipa / pinyin / hint。"""

    surface: str = Field(min_length=1)
    pronunciation: str = Field(
        min_length=1,
        description="IPA / 拼音 / provider 支持的任何标注（provider 决定语法）",
    )
    notes: str | None = None


class PronunciationLexicon(ContractModel):
    """一对（provider, language）的发音词典。entries surface 唯一。"""

    id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    provider_tier: TTSProviderTier | None = Field(
        default=None,
        description="null 表示跨 provider 通用；有值即绑定该层的标注格式",
    )
    entries: list[PronunciationEntry] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    created_at: datetime

    @model_validator(mode="after")
    def _check_unique_surface(self) -> "PronunciationLexicon":
        seen: set[str] = set()
        for e in self.entries:
            if e.surface in seen:
                raise ValueError(f"发音词典 surface 重复：{e.surface}")
            seen.add(e.surface)
        return self


class TTSWordTiming(ContractModel):
    """合成后的词级时间；跟 VF-402 SubtitleWord 不同——TTS 直接产 word onset，不
    需 forced alignment。confidence 通常来自 provider 内部对齐质量估计。"""

    text: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_span(self) -> "TTSWordTiming":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms 必须 ≥ start_ms")
        return self


class TTSManifest(ContractModel):
    """一次 TTS 合成的可重放 manifest（同 41 §11 精神：input digest + provider +
    tool_version + config → activity cache key）。

    input_text_hash 就是本次合成文本 + 语言 + voice_profile_id + style + target_duration
    + lexicon_id + seed 的组合哈希；由 domain 侧算出。
    """

    id: str = Field(min_length=1)
    sentence_id: str = Field(min_length=1, description="源脚本句 id 或翻译句 id")
    voice_profile_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    text_hash: str = Field(min_length=1, description="input text+config 的哈希")
    provider: str = Field(min_length=1)
    provider_tier: TTSProviderTier
    tool_version: str | None = None
    audio_artifact_id: str | None = Field(
        default=None,
        description="合成音频 artifact id；FAILED/UNCONFIGURED 时为 None",
    )
    duration_ms: int | None = Field(default=None, ge=0)
    word_timings: list[TTSWordTiming] = Field(default_factory=list)
    speed_used: float | None = Field(
        default=None,
        gt=0.0,
        description="实际使用的语速倍数（time fit 后）",
    )
    seed: int | None = None
    created_at: datetime
