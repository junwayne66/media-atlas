"""VF-406 provider-sdk 口型：Unconfigured / Fake / 零 GPU 导入 / provider→domain 非阻塞。"""

import ast
import inspect

import videoforge_provider_sdk.lipsync as lipsync_module
from videoforge_contracts import LipSyncEligibilityCriteria, LipSyncMode, LipSyncQAReport
from videoforge_domain import LipSyncAvailability, LipSyncSegmentFeatures, decide_lipsync
from videoforge_provider_sdk import (
    FakeLipSyncProvider,
    LipSyncErrorCode,
    LipSyncProvider,
    LipSyncRequest,
    LipSyncStatus,
    UnconfiguredLipSyncProvider,
)


def _req() -> LipSyncRequest:
    return LipSyncRequest(
        segment_id="s", start_ms=0, end_ms=3000,
        source_video_ref="artifact://video/src.mp4",
        dub_audio_ref="artifact://audio/dub.wav",
        face_bbox=(0.3, 0.2, 0.2, 0.3),
    )


def _fail_qa() -> LipSyncQAReport:
    return LipSyncQAReport(
        boundary_score=0.4, skin_tone_score=0.5, motion_score=0.4,
        identity_score=0.6, passed=False,
    )


def test_providers_satisfy_protocol():
    assert isinstance(FakeLipSyncProvider(), LipSyncProvider)
    assert isinstance(UnconfiguredLipSyncProvider(), LipSyncProvider)


def test_unconfigured_never_synthesizes():
    r = UnconfiguredLipSyncProvider().synthesize(_req())
    assert r.status is LipSyncStatus.UNCONFIGURED
    assert r.synthesized_artifact_id is None
    assert r.error_code is LipSyncErrorCode.MODEL_UNAVAILABLE


def test_fake_ok_produces_artifact_and_passing_qa():
    r = FakeLipSyncProvider().synthesize(_req())
    assert r.status is LipSyncStatus.OK
    assert r.synthesized_artifact_id == "fake-lipsync-s"
    assert r.qa is not None and r.qa.passed


def test_fake_fail_reports_synthesis_failed():
    r = FakeLipSyncProvider(fail=True).synthesize(_req())
    assert r.status is LipSyncStatus.FAILED
    assert r.error_code is LipSyncErrorCode.SYNTHESIS_FAILED
    assert r.synthesized_artifact_id is None


def test_fake_returns_injected_failing_qa():
    # Fake 不自行降级——原样返回 OK + 未过 QA，交 domain 决定降级
    r = FakeLipSyncProvider(qa=_fail_qa()).synthesize(_req())
    assert r.status is LipSyncStatus.OK
    assert r.qa is not None and not r.qa.passed


def test_provider_ok_but_failed_qa_drives_domain_downgrade():
    # provider→domain 非阻塞：合成"成功"但 QA 不过 → domain 自动降级，绝不停在 GPU
    result = FakeLipSyncProvider(qa=_fail_qa()).synthesize(_req())
    feat = LipSyncSegmentFeatures(
        face_count=1, face_height_ratio=0.3, occlusion_ratio=0.05,
        speaker_probability=0.9, head_turn_deg=10.0, duration_ms=3000,
        dub_aligned=True,
    )
    decision = decide_lipsync(
        segment_id="s", start_ms=0, end_ms=3000, features=feat,
        availability=LipSyncAvailability(can_broll_cover=True),
        criteria=LipSyncEligibilityCriteria(), mode=LipSyncMode.AUTO_ELIGIBLE,
        qa=result.qa, synthesized_artifact_id=result.synthesized_artifact_id,
    )
    from videoforge_contracts import LipSyncMethod
    assert decision.method is LipSyncMethod.BROLL_COVER
    assert decision.needs_review


def test_fake_deep_copies_and_is_deterministic():
    p = FakeLipSyncProvider()
    req = _req()
    a = p.synthesize(req)
    b = p.synthesize(req)
    assert (a.status, a.synthesized_artifact_id) == (b.status, b.synthesized_artifact_id)
    assert req.segment_id == "s"  # 输入未被改动


def test_fake_module_has_zero_gpu_imports():
    # 口型 Fake 承诺：零 GPU/模型/subprocess 导入
    tree = ast.parse(inspect.getsource(lipsync_module))
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
        f"lipsync provider 引入了非白名单模块: {imported - allowed}"
    )
