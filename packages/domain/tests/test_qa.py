"""QA 规则引擎 + 发布门：每规则真/假阳 + 阈值边界 + BLOCKER 拒发布 + MAJOR 数超阈升级。"""

from datetime import UTC, datetime

import pytest

from videoforge_contracts import QAFindingKind, QASeverity
from videoforge_domain import (
    DEFAULT_THRESHOLDS,
    AudioWindowSample,
    CaptionBoundingBox,
    MediaSampleInput,
    PublishGate,
    QAThresholds,
    VideoFrameSample,
    aggregate_qa_report,
    check_broll_ratio,
    check_caption_overlap,
    check_caption_safe_area,
    check_duration_match,
    check_loudness,
    detect_black_frames,
    detect_duplicate_frames,
    detect_frozen_frames,
    detect_voice_tail_cut,
    validate_publish_gate,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _frame(at: int, luma: float, ph: str) -> VideoFrameSample:
    return VideoFrameSample(at_ms=at, mean_luma=luma, phash=ph)


def _audio(
    at: int, dur: int, lufs: float = -14, tp: float = -3.0, voice: bool = False, tail: float = 0.01
) -> AudioWindowSample:
    return AudioWindowSample(
        at_ms=at,
        duration_ms=dur,
        lufs=lufs,
        true_peak_dbtp=tp,
        has_voice=voice,
        tail_amplitude=tail,
    )


def _caption(
    cid: str,
    at: int,
    dur: int,
    left: float = 10,
    top: float = 80,
    right: float = 90,
    bottom: float = 92,
) -> CaptionBoundingBox:
    return CaptionBoundingBox(
        caption_id=cid,
        at_ms=at,
        duration_ms=dur,
        left_pct=left,
        top_pct=top,
        right_pct=right,
        bottom_pct=bottom,
    )


# —— 视频规则 ——


def test_detect_black_frames_flags_dark_run() -> None:
    frames = [_frame(0, 100, "a"), _frame(100, 5, "b"), _frame(200, 3, "c"), _frame(300, 90, "d")]
    findings = detect_black_frames(frames)
    assert len(findings) == 1
    f = findings[0]
    assert f.kind is QAFindingKind.BLACK_FRAME and f.severity is QASeverity.BLOCKER
    assert f.at_ms == 100 and f.duration_ms == 100  # 覆盖 100..200


def test_detect_black_frames_ignores_bright() -> None:
    frames = [_frame(0, 100, "a"), _frame(100, 200, "b")]
    assert detect_black_frames(frames) == []


def test_detect_frozen_frames_flags_long_run() -> None:
    # 6 帧相同 phash → 冻帧
    frames = [_frame(i * 33, 128, "x") for i in range(6)] + [_frame(200, 128, "y")]
    findings = detect_frozen_frames(frames)
    assert findings and findings[0].kind is QAFindingKind.FROZEN_FRAME
    assert findings[0].severity is QASeverity.MAJOR


def test_detect_frozen_frames_below_threshold_passes() -> None:
    # 3 帧相同 phash（低于默认 6）→ 不判冻帧
    frames = [_frame(i * 33, 128, "x") for i in range(3)] + [_frame(100, 128, "y")]
    assert detect_frozen_frames(frames) == []


def test_detect_duplicate_frames_flags_adjacent() -> None:
    frames = [_frame(0, 100, "a"), _frame(33, 100, "a")]  # 相邻 phash 相同
    findings = detect_duplicate_frames(frames)
    assert len(findings) == 1
    assert findings[0].kind is QAFindingKind.DUPLICATE_FRAMES
    assert findings[0].severity is QASeverity.MINOR


# —— 音频规则 ——


def test_check_loudness_flags_out_of_range() -> None:
    # 目标 -14 ±2 → -20 越下界
    findings = check_loudness([_audio(0, 45000, lufs=-20, tp=-3)])
    kinds = {f.kind for f in findings}
    assert QAFindingKind.LOUDNESS_OUT_OF_RANGE in kinds


def test_check_loudness_flags_true_peak_clip() -> None:
    findings = check_loudness([_audio(0, 45000, lufs=-14, tp=0.5)])  # >-1 爆表
    kinds = {(f.kind, f.severity) for f in findings}
    assert (QAFindingKind.TRUE_PEAK_CLIP, QASeverity.BLOCKER) in kinds


def test_check_loudness_within_range_passes() -> None:
    assert check_loudness([_audio(0, 45000, lufs=-14, tp=-3)]) == []


def test_detect_voice_tail_cut_flags_end_voice() -> None:
    # 末窗有人声且尾部电平 >0.05
    windows = [_audio(0, 40000, voice=False, tail=0.0), _audio(40000, 5000, voice=True, tail=0.4)]
    findings = detect_voice_tail_cut(windows)
    assert findings and findings[0].kind is QAFindingKind.VOICE_TAIL_CUT
    assert findings[0].severity is QASeverity.BLOCKER


def test_detect_voice_tail_cut_ignores_silence_end() -> None:
    # 末窗无人声即通过
    windows = [_audio(0, 45000, voice=False, tail=0.001)]
    assert detect_voice_tail_cut(windows) == []


# —— 字幕规则 ——


def test_check_caption_safe_area_flags_out() -> None:
    # bottom 96 > safe_max 95 → 越界
    findings = check_caption_safe_area([_caption("c0", 0, 1500, bottom=96)])
    assert findings and findings[0].kind is QAFindingKind.CAPTION_OFF_SAFE_AREA


def test_check_caption_safe_area_within_passes() -> None:
    assert check_caption_safe_area([_caption("c0", 0, 1500)]) == []


def test_check_caption_overlap_flags_intersecting() -> None:
    caps = [_caption("c0", 0, 2000), _caption("c1", 1500, 2000)]  # 1500..2000 重叠
    findings = check_caption_overlap(caps)
    assert findings and findings[0].kind is QAFindingKind.CAPTION_OVERLAP


def test_check_caption_overlap_touching_ok() -> None:
    # 相接（a.end == b.start）不判重叠
    caps = [_caption("c0", 0, 1500), _caption("c1", 1500, 1500)]
    assert check_caption_overlap(caps) == []


# —— 构图 / 时长 ——


def test_check_broll_ratio_low_flagged() -> None:
    findings = check_broll_ratio(broll_duration_ms=1000, total_video_duration_ms=45000)
    assert findings and findings[0].kind is QAFindingKind.BROLL_RATIO_LOW


def test_check_broll_ratio_sufficient_passes() -> None:
    assert check_broll_ratio(broll_duration_ms=10000, total_video_duration_ms=45000) == []


def test_check_duration_match_exceeding_tolerance_flagged() -> None:
    findings = check_duration_match(timeline_duration_ms=45000, measured_duration_ms=45500)
    assert findings and findings[0].kind is QAFindingKind.DURATION_MISMATCH
    assert findings[0].severity is QASeverity.BLOCKER


def test_check_duration_match_within_tolerance_passes() -> None:
    # 50ms 差在 100ms 容差内
    assert check_duration_match(timeline_duration_ms=45000, measured_duration_ms=45050) == []


# —— 发布门 ——


def test_publish_gate_blocks_on_any_blocker() -> None:
    from videoforge_contracts import QAFinding

    findings = [
        QAFinding(id="f", kind=QAFindingKind.BLACK_FRAME, severity=QASeverity.BLOCKER, at_ms=0)
    ]
    assert validate_publish_gate(findings) is PublishGate.BLOCK


def test_publish_gate_blocks_on_too_many_majors() -> None:
    from videoforge_contracts import QAFinding

    findings = [
        QAFinding(
            id=f"f-{i}",
            kind=QAFindingKind.LOUDNESS_OUT_OF_RANGE,
            severity=QASeverity.MAJOR,
            at_ms=i * 1000,
        )
        for i in range(4)
    ]  # 4 > 默认 3
    assert validate_publish_gate(findings) is PublishGate.BLOCK


def test_publish_gate_passes_on_minor_only() -> None:
    from videoforge_contracts import QAFinding

    findings = [
        QAFinding(
            id="f", kind=QAFindingKind.CAPTION_OFF_SAFE_AREA, severity=QASeverity.MINOR, at_ms=0
        )
    ]
    assert validate_publish_gate(findings) is PublishGate.PASS


def test_publish_gate_passes_on_empty() -> None:
    assert validate_publish_gate([]) is PublishGate.PASS


# —— 聚合 aggregate_qa_report ——


def test_aggregate_clean_report_passes() -> None:
    input_data = MediaSampleInput(
        video_frames=[_frame(i * 33, 128, f"h{i}") for i in range(10)],
        audio_windows=[_audio(0, 45000, lufs=-14, tp=-3, voice=False, tail=0.001)],
        captions=[_caption("c0", 0, 1500)],
        broll_duration_ms=10000,
        total_video_duration_ms=45000,
        measured_duration_ms=45000,
    )
    report = aggregate_qa_report(
        input_data, report_id="r", timeline_id="tl", timeline_duration_ms=45000, created_at=_T0
    )
    assert report.pass_or_block is True
    assert report.findings == []


def test_aggregate_black_frame_blocks() -> None:
    input_data = MediaSampleInput(
        video_frames=[
            _frame(0, 100, "a"),
            _frame(100, 2, "b"),  # 黑帧
            _frame(200, 100, "c"),
        ],
        audio_windows=[_audio(0, 45000, voice=False, tail=0.001)],
        measured_duration_ms=45000,
    )
    report = aggregate_qa_report(
        input_data, report_id="r", timeline_id="tl", timeline_duration_ms=45000, created_at=_T0
    )
    assert report.pass_or_block is False
    assert any(f.kind is QAFindingKind.BLACK_FRAME for f in report.findings)


def test_duplicate_caption_ids_do_not_crash_aggregation() -> None:
    # 回归：真实分析器可能产出重复 caption_id；aggregate 不得因内部 finding-id 撞车而崩。
    input_data = MediaSampleInput(
        video_frames=[_frame(i * 33, 128, f"h{i}") for i in range(10)],
        audio_windows=[_audio(0, 45000, voice=False, tail=0.001)],
        # 两条都越安全区（bottom=96），且 caption_id 相同
        captions=[_caption("dup", 0, 1500, bottom=96), _caption("dup", 2000, 1500, bottom=96)],
        broll_duration_ms=10000,
        total_video_duration_ms=45000,
        measured_duration_ms=45000,
    )
    report = aggregate_qa_report(
        input_data, report_id="r", timeline_id="tl", timeline_duration_ms=45000, created_at=_T0
    )
    safe_findings = [f for f in report.findings if f.kind is QAFindingKind.CAPTION_OFF_SAFE_AREA]
    assert len(safe_findings) == 2  # 两条 finding；id 加 enumerate 索引保唯一
    assert len({f.id for f in safe_findings}) == 2


def test_contract_rejects_pass_true_with_blocker() -> None:
    # 回归：手工构造 QAReport 声称 pass_or_block=True 但含 BLOCKER —— 契约层拒绝
    from pydantic import ValidationError

    from videoforge_contracts import QAFinding, QAReport

    with pytest.raises(ValidationError, match="pass_or_block"):
        QAReport(
            id="r",
            timeline_id="tl",
            findings=[
                QAFinding(
                    id="f", kind=QAFindingKind.BLACK_FRAME, severity=QASeverity.BLOCKER, at_ms=0
                )
            ],
            timeline_duration_ms=45000,
            measured_duration_ms=45000,
            pass_or_block=True,  # 与 BLOCKER 冲突
            created_at=_T0,
        )


def test_contract_accepts_pass_false_with_blocker() -> None:
    from videoforge_contracts import QAFinding, QAReport

    report = QAReport(
        id="r",
        timeline_id="tl",
        findings=[
            QAFinding(id="f", kind=QAFindingKind.BLACK_FRAME, severity=QASeverity.BLOCKER, at_ms=0)
        ],
        timeline_duration_ms=45000,
        measured_duration_ms=45000,
        pass_or_block=False,
        created_at=_T0,
    )
    assert report.pass_or_block is False


def test_thresholds_are_customizable() -> None:
    # 收紧阈值 → 原本通过的样本被判黑帧
    strict = QAThresholds(black_luma_max=200)
    frames = [_frame(0, 100, "a")]  # 100 <= 200
    findings = detect_black_frames(frames, strict)
    assert findings and findings[0].kind is QAFindingKind.BLACK_FRAME
    # 默认阈值不误判
    assert detect_black_frames(frames, DEFAULT_THRESHOLDS) == []
