"""QA 规则引擎 + 发布门（docs/modules/42 §11）。纯函数，确定性。

规则接受结构化"帧样本 / 音频样本 / 字幕样本 / 时长"作为输入（来自 provider-sdk MediaAnalyzer
的 Fake 或真实检测器），输出 QAFinding 列表。**规则本身不做 I/O，不解码媒体**——媒体分析属
provider-sdk 端口后置。这样纯域可复现、可 fuzz、可离线验证。

发布门：`validate_publish_gate` —— BLOCKER 一处即拒；MAJOR 数超阈值升级为拒；其余可发布。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from videoforge_contracts import (
    QAFinding,
    QAFindingKind,
    QAReport,
    QASeverity,
)

# 默认阈值——首期从 video-autopilot-kit 常识取值，可通过 QAThresholds 覆盖
_DEFAULT_BLACK_LUMA_MAX = 8.0  # 黑帧亮度阈值（0-255）
_DEFAULT_FROZEN_MIN_FRAMES = 6  # 冻帧持续帧数（0.2s @30fps）
_DEFAULT_FLICKER_LUMA_DELTA = 60.0  # 相邻帧亮度差 → 频闪
_DEFAULT_LOUDNESS_TARGET_LUFS = -14.0
_DEFAULT_LOUDNESS_TOL_LUFS = 2.0
_DEFAULT_TRUE_PEAK_MAX_DBTP = -1.0  # dBTP，超过判定爆表
_DEFAULT_SAFE_AREA_MIN_PCT = 5.0  # 边距百分比：<5% 或 >95% 视为出安全区
_DEFAULT_SAFE_AREA_MAX_PCT = 95.0
_DEFAULT_BROLL_MIN_RATIO = 0.15  # V2 B-roll 占比 <15% 判不足
_DEFAULT_DURATION_TOLERANCE_MS = 100  # Timeline vs 实测差 >100ms 拒
_DEFAULT_MAX_MAJOR_BEFORE_BLOCK = 3


@dataclass(frozen=True)
class QAThresholds:
    """QA 阈值配置。可版本化，供不同发布平台/频道使用。"""

    black_luma_max: float = _DEFAULT_BLACK_LUMA_MAX
    frozen_min_frames: int = _DEFAULT_FROZEN_MIN_FRAMES
    flicker_luma_delta: float = _DEFAULT_FLICKER_LUMA_DELTA
    loudness_target_lufs: float = _DEFAULT_LOUDNESS_TARGET_LUFS
    loudness_tol_lufs: float = _DEFAULT_LOUDNESS_TOL_LUFS
    true_peak_max_dbtp: float = _DEFAULT_TRUE_PEAK_MAX_DBTP
    safe_area_min_pct: float = _DEFAULT_SAFE_AREA_MIN_PCT
    safe_area_max_pct: float = _DEFAULT_SAFE_AREA_MAX_PCT
    broll_min_ratio: float = _DEFAULT_BROLL_MIN_RATIO
    duration_tolerance_ms: int = _DEFAULT_DURATION_TOLERANCE_MS
    max_major_before_block: int = _DEFAULT_MAX_MAJOR_BEFORE_BLOCK


DEFAULT_THRESHOLDS = QAThresholds()


# ————————————————————————————————————————————————————————————————
# 输入样本（provider-sdk MediaAnalyzer 产出 → domain 消费）
# ————————————————————————————————————————————————————————————————


@dataclass(frozen=True)
class VideoFrameSample:
    """一帧的度量：亮度均值 + phash（供重复帧/冻帧检测）。"""

    at_ms: int
    mean_luma: float  # 0-255
    phash: str  # 感知哈希，供帧间比对


@dataclass(frozen=True)
class AudioWindowSample:
    """一个时间窗的音频度量：LUFS/True Peak/是否含人声/尾部电平。"""

    at_ms: int
    duration_ms: int
    lufs: float
    true_peak_dbtp: float
    has_voice: bool
    tail_amplitude: float  # 尾部 20ms 电平（0-1），供尾切检测


@dataclass(frozen=True)
class CaptionBoundingBox:
    """字幕在画面上的归一化包围盒（0-100 百分比）+ 时间范围。"""

    caption_id: str
    at_ms: int
    duration_ms: int
    left_pct: float
    top_pct: float
    right_pct: float
    bottom_pct: float


@dataclass(frozen=True)
class MediaSampleInput:
    """一次 QA 分析的完整输入。字段可选：只跑视频规则时 audio_samples 可为空。"""

    video_frames: list[VideoFrameSample] = field(default_factory=list)
    audio_windows: list[AudioWindowSample] = field(default_factory=list)
    captions: list[CaptionBoundingBox] = field(default_factory=list)
    broll_duration_ms: int = 0
    total_video_duration_ms: int = 0
    measured_duration_ms: int = 0


class PublishGate(StrEnum):
    """发布门结论。"""

    PASS = "PASS"
    BLOCK = "BLOCK"


# ————————————————————————————————————————————————————————————————
# 规则实现（各自可单元测试）
# ————————————————————————————————————————————————————————————————


def detect_black_frames(
    frames: list[VideoFrameSample],
    thresholds: QAThresholds = DEFAULT_THRESHOLDS,
) -> list[QAFinding]:
    """连续 mean_luma ≤ 阈值 的帧段 → BLACK_FRAME 发现。BLOCKER 严重级。"""
    findings: list[QAFinding] = []
    if not frames:
        return findings
    idx = 0
    run_start: int | None = None
    run_last_ms: int | None = None
    for frame in frames:
        if frame.mean_luma <= thresholds.black_luma_max:
            if run_start is None:
                run_start = frame.at_ms
            run_last_ms = frame.at_ms
        else:
            if run_start is not None:
                findings.append(
                    QAFinding(
                        id=f"blk-{idx}",
                        kind=QAFindingKind.BLACK_FRAME,
                        severity=QASeverity.BLOCKER,
                        at_ms=run_start,
                        duration_ms=max(0, (run_last_ms or run_start) - run_start),
                        evidence={"threshold": thresholds.black_luma_max},
                    )
                )
                idx += 1
            run_start = None
            run_last_ms = None
    if run_start is not None:
        findings.append(
            QAFinding(
                id=f"blk-{idx}",
                kind=QAFindingKind.BLACK_FRAME,
                severity=QASeverity.BLOCKER,
                at_ms=run_start,
                duration_ms=max(0, (run_last_ms or run_start) - run_start),
                evidence={"threshold": thresholds.black_luma_max},
            )
        )
    return findings


def detect_frozen_frames(
    frames: list[VideoFrameSample],
    thresholds: QAThresholds = DEFAULT_THRESHOLDS,
) -> list[QAFinding]:
    """连续 N 帧 phash 相同 → FROZEN_FRAME。MAJOR。"""
    findings: list[QAFinding] = []
    if len(frames) < thresholds.frozen_min_frames:
        return findings
    idx = 0
    run_len = 1
    run_start = frames[0].at_ms
    for i in range(1, len(frames)):
        if frames[i].phash == frames[i - 1].phash:
            run_len += 1
        else:
            if run_len >= thresholds.frozen_min_frames:
                findings.append(
                    QAFinding(
                        id=f"frz-{idx}",
                        kind=QAFindingKind.FROZEN_FRAME,
                        severity=QASeverity.MAJOR,
                        at_ms=run_start,
                        duration_ms=frames[i - 1].at_ms - run_start,
                        evidence={
                            "frame_count": run_len,
                            "min_frames": thresholds.frozen_min_frames,
                        },
                    )
                )
                idx += 1
            run_len = 1
            run_start = frames[i].at_ms
    if run_len >= thresholds.frozen_min_frames:
        findings.append(
            QAFinding(
                id=f"frz-{idx}",
                kind=QAFindingKind.FROZEN_FRAME,
                severity=QASeverity.MAJOR,
                at_ms=run_start,
                duration_ms=frames[-1].at_ms - run_start,
                evidence={"frame_count": run_len, "min_frames": thresholds.frozen_min_frames},
            )
        )
    return findings


def detect_duplicate_frames(
    frames: list[VideoFrameSample],
    _: QAThresholds = DEFAULT_THRESHOLDS,
) -> list[QAFinding]:
    """相邻两帧 phash 完全相同（非冻帧的短暂重复）→ DUPLICATE_FRAMES。MINOR。"""
    findings: list[QAFinding] = []
    if len(frames) < 2:
        return findings
    for i in range(1, len(frames)):
        if frames[i].phash == frames[i - 1].phash:
            findings.append(
                QAFinding(
                    id=f"dup-{i}",
                    kind=QAFindingKind.DUPLICATE_FRAMES,
                    severity=QASeverity.MINOR,
                    at_ms=frames[i].at_ms,
                    duration_ms=0,
                    evidence={"prev_at_ms": frames[i - 1].at_ms},
                )
            )
    return findings


def check_loudness(
    audio_windows: list[AudioWindowSample],
    thresholds: QAThresholds = DEFAULT_THRESHOLDS,
) -> list[QAFinding]:
    """响度越出目标±容差 → LOUDNESS_OUT_OF_RANGE MAJOR；True Peak 爆表 → TRUE_PEAK_CLIP BLOCKER。"""
    findings: list[QAFinding] = []
    if not audio_windows:
        return findings
    # 用最长窗（通常是整段）代表整体响度；简化模型
    longest = max(audio_windows, key=lambda w: w.duration_ms)
    lo = thresholds.loudness_target_lufs - thresholds.loudness_tol_lufs
    hi = thresholds.loudness_target_lufs + thresholds.loudness_tol_lufs
    if longest.lufs < lo or longest.lufs > hi:
        findings.append(
            QAFinding(
                id="loud-0",
                kind=QAFindingKind.LOUDNESS_OUT_OF_RANGE,
                severity=QASeverity.MAJOR,
                at_ms=longest.at_ms,
                duration_ms=longest.duration_ms,
                evidence={"lufs": longest.lufs, "target_min": lo, "target_max": hi},
            )
        )
    for i, w in enumerate(audio_windows):
        if w.true_peak_dbtp > thresholds.true_peak_max_dbtp:
            findings.append(
                QAFinding(
                    id=f"tp-{i}",
                    kind=QAFindingKind.TRUE_PEAK_CLIP,
                    severity=QASeverity.BLOCKER,
                    at_ms=w.at_ms,
                    duration_ms=w.duration_ms,
                    evidence={
                        "true_peak_dbtp": w.true_peak_dbtp,
                        "max_dbtp": thresholds.true_peak_max_dbtp,
                    },
                )
            )
    return findings


def detect_voice_tail_cut(
    audio_windows: list[AudioWindowSample],
    _: QAThresholds = DEFAULT_THRESHOLDS,
) -> list[QAFinding]:
    """末窗仍含人声且尾部电平 >0.05（未渐弱） → VOICE_TAIL_CUT。BLOCKER（发布纪律强要求）。"""
    if not audio_windows:
        return []
    last = audio_windows[-1]
    if last.has_voice and last.tail_amplitude > 0.05:
        return [
            QAFinding(
                id="tail-0",
                kind=QAFindingKind.VOICE_TAIL_CUT,
                severity=QASeverity.BLOCKER,
                at_ms=last.at_ms + last.duration_ms,
                duration_ms=0,
                evidence={"tail_amplitude": last.tail_amplitude},
            )
        ]
    return []


def check_caption_safe_area(
    captions: list[CaptionBoundingBox],
    thresholds: QAThresholds = DEFAULT_THRESHOLDS,
) -> list[QAFinding]:
    """任意边越出安全区（<min 或 >max %）→ CAPTION_OFF_SAFE_AREA MINOR。id 加索引防重复。"""
    findings: list[QAFinding] = []
    for i, cap in enumerate(captions):
        if (
            cap.left_pct < thresholds.safe_area_min_pct
            or cap.right_pct > thresholds.safe_area_max_pct
            or cap.top_pct < thresholds.safe_area_min_pct
            or cap.bottom_pct > thresholds.safe_area_max_pct
        ):
            findings.append(
                QAFinding(
                    id=f"safe-{i}-{cap.caption_id}",
                    kind=QAFindingKind.CAPTION_OFF_SAFE_AREA,
                    severity=QASeverity.MINOR,
                    at_ms=cap.at_ms,
                    duration_ms=cap.duration_ms,
                    track_ref="v4",
                    evidence={
                        "left": cap.left_pct,
                        "right": cap.right_pct,
                        "top": cap.top_pct,
                        "bottom": cap.bottom_pct,
                        "safe_min": thresholds.safe_area_min_pct,
                        "safe_max": thresholds.safe_area_max_pct,
                    },
                )
            )
    return findings


def check_caption_overlap(captions: list[CaptionBoundingBox]) -> list[QAFinding]:
    """同一时刻多条字幕的时间范围有交集 → CAPTION_OVERLAP MAJOR。"""
    findings: list[QAFinding] = []
    for i in range(len(captions)):
        for j in range(i + 1, len(captions)):
            a, b = captions[i], captions[j]
            a_end = a.at_ms + a.duration_ms
            b_end = b.at_ms + b.duration_ms
            if a.at_ms < b_end and b.at_ms < a_end:
                findings.append(
                    QAFinding(
                        id=f"cap-ov-{i}-{j}",
                        kind=QAFindingKind.CAPTION_OVERLAP,
                        severity=QASeverity.MAJOR,
                        at_ms=max(a.at_ms, b.at_ms),
                        duration_ms=min(a_end, b_end) - max(a.at_ms, b.at_ms),
                        track_ref="v4",
                        evidence={"a": a.caption_id, "b": b.caption_id},
                    )
                )
    return findings


def check_broll_ratio(
    broll_duration_ms: int,
    total_video_duration_ms: int,
    thresholds: QAThresholds = DEFAULT_THRESHOLDS,
) -> list[QAFinding]:
    """B-roll 占比 < 阈值 → BROLL_RATIO_LOW MINOR。"""
    if total_video_duration_ms <= 0:
        return []
    ratio = broll_duration_ms / total_video_duration_ms
    if ratio < thresholds.broll_min_ratio:
        return [
            QAFinding(
                id="broll-0",
                kind=QAFindingKind.BROLL_RATIO_LOW,
                severity=QASeverity.MINOR,
                at_ms=0,
                duration_ms=total_video_duration_ms,
                evidence={"ratio": round(ratio, 4), "min_ratio": thresholds.broll_min_ratio},
            )
        ]
    return []


def check_duration_match(
    timeline_duration_ms: int,
    measured_duration_ms: int,
    thresholds: QAThresholds = DEFAULT_THRESHOLDS,
) -> list[QAFinding]:
    """Timeline 声明时长与实测差 > 容差 → DURATION_MISMATCH BLOCKER。"""
    diff = abs(timeline_duration_ms - measured_duration_ms)
    if diff > thresholds.duration_tolerance_ms:
        return [
            QAFinding(
                id="dur-0",
                kind=QAFindingKind.DURATION_MISMATCH,
                severity=QASeverity.BLOCKER,
                at_ms=0,
                duration_ms=diff,
                evidence={
                    "timeline_ms": timeline_duration_ms,
                    "measured_ms": measured_duration_ms,
                    "tolerance_ms": thresholds.duration_tolerance_ms,
                },
            )
        ]
    return []


# ————————————————————————————————————————————————————————————————
# 聚合 + 发布门
# ————————————————————————————————————————————————————————————————


def aggregate_qa_report(
    input_data: MediaSampleInput,
    *,
    report_id: str,
    timeline_id: str,
    timeline_duration_ms: int,
    created_at: datetime,
    render_manifest_id: str | None = None,
    thresholds: QAThresholds = DEFAULT_THRESHOLDS,
) -> QAReport:
    """跑全部规则、聚合为 QAReport；pass_or_block 由 publish gate 决定。"""
    findings: list[QAFinding] = []
    findings.extend(detect_black_frames(input_data.video_frames, thresholds))
    findings.extend(detect_frozen_frames(input_data.video_frames, thresholds))
    findings.extend(detect_duplicate_frames(input_data.video_frames, thresholds))
    findings.extend(check_loudness(input_data.audio_windows, thresholds))
    findings.extend(detect_voice_tail_cut(input_data.audio_windows, thresholds))
    findings.extend(check_caption_safe_area(input_data.captions, thresholds))
    findings.extend(check_caption_overlap(input_data.captions))
    findings.extend(
        check_broll_ratio(
            input_data.broll_duration_ms,
            input_data.total_video_duration_ms,
            thresholds,
        )
    )
    findings.extend(
        check_duration_match(
            timeline_duration_ms,
            input_data.measured_duration_ms,
            thresholds,
        )
    )

    gate = validate_publish_gate(findings, thresholds=thresholds)
    return QAReport(
        id=report_id,
        timeline_id=timeline_id,
        render_manifest_id=render_manifest_id,
        findings=findings,
        timeline_duration_ms=timeline_duration_ms,
        measured_duration_ms=input_data.measured_duration_ms,
        pass_or_block=(gate is PublishGate.PASS),
        created_at=created_at,
    )


def validate_publish_gate(
    findings: list[QAFinding],
    *,
    thresholds: QAThresholds = DEFAULT_THRESHOLDS,
) -> PublishGate:
    """发布门：BLOCKER 一处即拒；MAJOR 数超阈值升级为拒；其余 PASS。"""
    blockers = [f for f in findings if f.severity is QASeverity.BLOCKER]
    if blockers:
        return PublishGate.BLOCK
    majors = [f for f in findings if f.severity is QASeverity.MAJOR]
    if len(majors) > thresholds.max_major_before_block:
        return PublishGate.BLOCK
    return PublishGate.PASS


__all__ = [
    "DEFAULT_THRESHOLDS",
    "AudioWindowSample",
    "CaptionBoundingBox",
    "MediaSampleInput",
    "PublishGate",
    "QAThresholds",
    "VideoFrameSample",
    "aggregate_qa_report",
    "check_broll_ratio",
    "check_caption_overlap",
    "check_caption_safe_area",
    "check_duration_match",
    "check_loudness",
    "detect_black_frames",
    "detect_duplicate_frames",
    "detect_frozen_frames",
    "detect_voice_tail_cut",
    "validate_publish_gate",
]
