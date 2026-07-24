"""VF-405 provider-sdk 音频合成：Unconfigured / Fake / True Peak Gate / 零 I/O。"""

import ast
import inspect
from datetime import UTC, datetime

import videoforge_provider_sdk.audio_mix as audio_mix_module
from videoforge_contracts import (
    AudioMixPlan,
    AudioMixTrack,
    AudioMixTrackKind,
    LoudnessTarget,
)
from videoforge_provider_sdk import (
    AudioMixErrorCode,
    AudioMixProvider,
    AudioMixRequest,
    AudioMixStatus,
    FakeAudioMixProvider,
    UnconfiguredAudioMixProvider,
)

_T0 = datetime(2026, 7, 24, tzinfo=UTC)


def _plan(*, lufs: float = -14.0, tol: float = 2.0,
          true_peak: float = -1.0) -> AudioMixPlan:
    return AudioMixPlan(
        id="am",
        tracks=[AudioMixTrack(
            id="dub", kind=AudioMixTrackKind.VOICE_DUB, start_ms=0, end_ms=8000,
        )],
        loudness_target=LoudnessTarget(
            lufs=lufs, lufs_tolerance=tol, true_peak_max_dbtp=true_peak,
        ),
        total_duration_ms=8000, created_at=_T0,
    )


def test_providers_satisfy_protocol():
    assert isinstance(FakeAudioMixProvider(), AudioMixProvider)
    assert isinstance(UnconfiguredAudioMixProvider(), AudioMixProvider)


def test_unconfigured_never_mixes():
    r = UnconfiguredAudioMixProvider().mix(AudioMixRequest(_plan()))
    assert r.status is AudioMixStatus.UNCONFIGURED
    assert r.output_artifact_id is None
    assert r.error_code is AudioMixErrorCode.ENGINE_UNAVAILABLE


def test_fake_ok_with_compliant_measurements():
    r = FakeAudioMixProvider().mix(AudioMixRequest(_plan()))
    assert r.status is AudioMixStatus.OK
    assert r.output_artifact_id == "fake-mix-am"
    assert r.true_peak_ok is True
    assert r.loudness_in_tolerance is True
    assert r.measured is not None


def test_fake_true_peak_gate_blocks_clip():
    # 注入 True Peak 0.5 dBTP 超硬顶 -1 → §9 Gate FAILED
    r = FakeAudioMixProvider(measured_true_peak_dbtp=0.5).mix(AudioMixRequest(_plan()))
    assert r.status is AudioMixStatus.FAILED
    assert r.error_code is AudioMixErrorCode.TRUE_PEAK_EXCEEDED
    assert r.true_peak_ok is False
    assert r.output_artifact_id is None


def test_fake_true_peak_boundary_exactly_at_limit_passes():
    # 恰好等于硬顶（≤）→ 通过
    r = FakeAudioMixProvider(measured_true_peak_dbtp=-1.0).mix(AudioMixRequest(_plan()))
    assert r.status is AudioMixStatus.OK
    assert r.true_peak_ok is True


def test_fake_loudness_out_of_tolerance_warns_but_ok():
    # 响度 -18 偏离目标 -14±2 → 不在容差，但 True Peak 过 → 仍 OK + warning
    r = FakeAudioMixProvider(measured_lufs=-18.0).mix(AudioMixRequest(_plan()))
    assert r.status is AudioMixStatus.OK
    assert r.loudness_in_tolerance is False
    assert any("响度" in w for w in r.warnings)


def test_fake_loudness_tolerance_boundary():
    # 差值恰好等于容差（≤）→ 在容差内
    r = FakeAudioMixProvider(measured_lufs=-16.0).mix(
        AudioMixRequest(_plan(lufs=-14.0, tol=2.0))
    )
    assert r.loudness_in_tolerance is True


def test_fake_is_deterministic():
    p = FakeAudioMixProvider()
    a = p.mix(AudioMixRequest(_plan()))
    b = p.mix(AudioMixRequest(_plan()))
    assert (a.status, a.output_artifact_id, a.measured) == (
        b.status, b.output_artifact_id, b.measured
    )


def test_fake_module_has_zero_io_imports():
    # §9 Fake 承诺：零 subprocess / 不 import 真实音频/DSP 库。
    # 用 AST 检查真实 import（不误伤 docstring 里描述"不做什么"的散文）。
    tree = ast.parse(inspect.getsource(audio_mix_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {
        "__future__", "copy", "dataclasses", "enum", "typing",
        "videoforge_contracts",
    }
    assert imported <= allowed, (
        f"audio_mix provider 引入了非白名单模块: {imported - allowed}"
    )
