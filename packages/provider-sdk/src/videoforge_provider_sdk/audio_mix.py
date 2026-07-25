"""音频合成端口 + Fake（docs/modules/43 §9：分轨/Ducking/响度/Room Tone → 混音 + 测量）。

`mix(plan) -> AudioArtifact + measured loudness`。真实混音/响度测量（ffmpeg loudnorm +
ebur128 + De-esser/EQ/压缩 + Room Tone）需真实引擎 → stop-condition 延后。

**True Peak Gate（§9 硬要求）**：测得 True Peak 超 `loudness_target.true_peak_max_dbtp`
→ 状态 `FAILED` + `TRUE_PEAK_EXCEEDED`（与 QA VF-309 的 TRUE_PEAK_CLIP BLOCKER 对齐，
提前在合成层拦，绝不"混出爆音还当成功"）。

`FakeAudioMixProvider` 用构造注入的测量值（像 VF-309 FakeMediaAnalyzer 注入 samples），
**零 I/O、零 subprocess、不 import ffmpeg/ebur128**——只对注入值与目标做纯比较。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from videoforge_contracts import AudioMixPlan


class AudioMixStatus(StrEnum):
    OK = "OK"
    FAILED = "FAILED"  # 含 True Peak Gate 未过
    UNCONFIGURED = "UNCONFIGURED"


class AudioMixErrorCode(StrEnum):
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    TRUE_PEAK_EXCEEDED = "TRUE_PEAK_EXCEEDED"  # §9 True Peak Gate 硬顶
    MIX_FAILED = "MIX_FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MeasuredLoudness:
    """成片重新测量的响度（§11：完成后重新提取测量，不信中间时间线）。"""

    integrated_lufs: float
    true_peak_dbtp: float


@dataclass(frozen=True)
class AudioMixRequest:
    plan: AudioMixPlan


@dataclass(frozen=True)
class AudioMixResult:
    status: AudioMixStatus
    output_artifact_id: str | None = None
    measured: MeasuredLoudness | None = None
    true_peak_ok: bool = False
    loudness_in_tolerance: bool = False
    error_code: AudioMixErrorCode | None = None
    error_detail: str | None = None
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class AudioMixProvider(Protocol):
    """§9 音频合成端口。"""

    name: str

    def mix(self, request: AudioMixRequest) -> AudioMixResult: ...

    def health_check(self) -> AudioMixResult: ...


class UnconfiguredAudioMixProvider:
    """诚实占位：无真实混音/测量引擎，绝不产出音频（真引擎属 stop-condition 延后）。"""

    def __init__(self, *, name: str = "audio_mix.unconfigured") -> None:
        self.name = name

    def mix(self, request: AudioMixRequest) -> AudioMixResult:
        return AudioMixResult(
            status=AudioMixStatus.UNCONFIGURED,
            error_code=AudioMixErrorCode.ENGINE_UNAVAILABLE,
            error_detail=f"provider {self.name!r} 未配置真实混音/响度引擎",
        )

    def health_check(self) -> AudioMixResult:
        return AudioMixResult(
            status=AudioMixStatus.UNCONFIGURED,
            error_code=AudioMixErrorCode.ENGINE_UNAVAILABLE,
        )


class FakeAudioMixProvider:
    """确定性 Fake：用构造注入的测量值与 plan.loudness_target 做纯比较。

    - **零 I/O、零 subprocess、不 import 任何真实音频库**（grep 可验）。
    - True Peak 超目标 → FAILED + TRUE_PEAK_EXCEEDED（§9 Gate；不当成功）。
    - `loudness_in_tolerance` = |measured_lufs − target.lufs| ≤ target.lufs_tolerance。
    - 默认注入值合规（-14 LUFS / -1.5 dBTP）；测试可注入越界值验 Gate。
    - deep-copy 输入；无内部可变状态。
    """

    def __init__(
        self,
        *,
        name: str = "audio_mix.fake",
        measured_lufs: float = -14.0,
        measured_true_peak_dbtp: float = -1.5,
    ) -> None:
        self.name = name
        self.measured_lufs = measured_lufs
        self.measured_true_peak_dbtp = measured_true_peak_dbtp

    def mix(self, request: AudioMixRequest) -> AudioMixResult:
        req = deepcopy(request)
        target = req.plan.loudness_target
        measured = MeasuredLoudness(
            integrated_lufs=self.measured_lufs,
            true_peak_dbtp=self.measured_true_peak_dbtp,
        )
        true_peak_ok = self.measured_true_peak_dbtp <= target.true_peak_max_dbtp
        loudness_in_tolerance = abs(self.measured_lufs - target.lufs) <= target.lufs_tolerance
        if not true_peak_ok:
            return AudioMixResult(
                status=AudioMixStatus.FAILED,
                measured=measured,
                true_peak_ok=False,
                loudness_in_tolerance=loudness_in_tolerance,
                error_code=AudioMixErrorCode.TRUE_PEAK_EXCEEDED,
                error_detail=(
                    f"True Peak {self.measured_true_peak_dbtp:.2f} dBTP 超硬顶 "
                    f"{target.true_peak_max_dbtp:.2f} dBTP（§9 Gate 必须通过）"
                ),
            )
        warnings = ["Fake 音频合成：非真实混音/测量，仅供 pipeline 开发"]
        if not loudness_in_tolerance:
            warnings.append(
                f"响度 {self.measured_lufs:.1f} LUFS 偏离目标 {target.lufs:.1f}"
                f"±{target.lufs_tolerance:.1f}（需 loudnorm 二次修正）"
            )
        return AudioMixResult(
            status=AudioMixStatus.OK,
            output_artifact_id=f"fake-mix-{req.plan.id}",
            measured=measured,
            true_peak_ok=True,
            loudness_in_tolerance=loudness_in_tolerance,
            warnings=warnings,
        )

    def health_check(self) -> AudioMixResult:
        return AudioMixResult(status=AudioMixStatus.OK)


__all__ = [
    "AudioMixErrorCode",
    "AudioMixProvider",
    "AudioMixRequest",
    "AudioMixResult",
    "AudioMixStatus",
    "FakeAudioMixProvider",
    "MeasuredLoudness",
    "UnconfiguredAudioMixProvider",
]
