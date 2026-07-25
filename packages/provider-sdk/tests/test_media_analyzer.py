"""媒体分析端口：Unconfigured 诚实 + Fake 端到端 → domain QA 规则 → 发布门。"""

from datetime import UTC, datetime

from videoforge_domain import (
    AudioWindowSample,
    CaptionBoundingBox,
    MediaSampleInput,
    PublishGate,
    VideoFrameSample,
    aggregate_qa_report,
    validate_publish_gate,
)
from videoforge_provider_sdk import (
    AudioWindow,
    CaptionBBox,
    FakeMediaAnalyzerProvider,
    FrameSample,
    MediaAnalysisRequest,
    MediaAnalyzerErrorCode,
    MediaAnalyzerProvider,
    MediaAnalyzerStatus,
    UnconfiguredMediaAnalyzerProvider,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def test_protocol_conformance() -> None:
    assert isinstance(FakeMediaAnalyzerProvider(), MediaAnalyzerProvider)
    assert isinstance(UnconfiguredMediaAnalyzerProvider(), MediaAnalyzerProvider)


def test_unconfigured_is_honest() -> None:
    prov = UnconfiguredMediaAnalyzerProvider()
    result = prov.analyze(MediaAnalysisRequest(resolved_path="/staging/final.mp4"))
    assert result.status is MediaAnalyzerStatus.UNCONFIGURED
    assert result.error_code is MediaAnalyzerErrorCode.UNCONFIGURED
    assert result.frame_samples == []  # 绝不静默造样本
    assert prov.health_check().status is MediaAnalyzerStatus.UNCONFIGURED


def test_fake_end_to_end_clean_input_passes_gate() -> None:
    # 无问题的 fixture → domain 聚合 → PASS
    fake = FakeMediaAnalyzerProvider(
        frame_samples=[FrameSample(at_ms=i * 33, mean_luma=128, phash=f"h{i}") for i in range(10)],
        audio_windows=[
            AudioWindow(
                at_ms=0,
                duration_ms=45000,
                lufs=-14.0,
                true_peak_dbtp=-3.0,
                has_voice=False,
                tail_amplitude=0.001,
            )
        ],
        captions=[
            CaptionBBox(
                caption_id="c0",
                at_ms=0,
                duration_ms=1500,
                left_pct=10,
                top_pct=80,
                right_pct=90,
                bottom_pct=92,
            )
        ],
        measured_duration_ms=45000,
        broll_duration_ms=10000,
        total_video_duration_ms=45000,
    )
    result = fake.analyze(MediaAnalysisRequest(resolved_path="/staging/final.mp4"))
    assert result.ok

    # 组装 domain 输入（provider dataclass 与 domain dataclass 同形，靠调用方映射）
    input_data = MediaSampleInput(
        video_frames=[
            VideoFrameSample(at_ms=s.at_ms, mean_luma=s.mean_luma, phash=s.phash)
            for s in result.frame_samples
        ],
        audio_windows=[
            AudioWindowSample(
                at_ms=w.at_ms,
                duration_ms=w.duration_ms,
                lufs=w.lufs,
                true_peak_dbtp=w.true_peak_dbtp,
                has_voice=w.has_voice,
                tail_amplitude=w.tail_amplitude,
            )
            for w in result.audio_windows
        ],
        captions=[
            CaptionBoundingBox(
                caption_id=c.caption_id,
                at_ms=c.at_ms,
                duration_ms=c.duration_ms,
                left_pct=c.left_pct,
                top_pct=c.top_pct,
                right_pct=c.right_pct,
                bottom_pct=c.bottom_pct,
            )
            for c in result.captions
        ],
        broll_duration_ms=result.broll_duration_ms,
        total_video_duration_ms=result.total_video_duration_ms,
        measured_duration_ms=result.measured_duration_ms,
    )
    report = aggregate_qa_report(
        input_data, report_id="r", timeline_id="tl", timeline_duration_ms=45000, created_at=_T0
    )
    assert report.pass_or_block is True
    assert validate_publish_gate(report.findings) is PublishGate.PASS


def test_fake_end_to_end_black_frame_blocks_gate() -> None:
    # 黑帧样本 → BLOCKER → BLOCK
    fake = FakeMediaAnalyzerProvider(
        frame_samples=[
            FrameSample(at_ms=0, mean_luma=100, phash="a"),
            FrameSample(at_ms=100, mean_luma=2, phash="b"),  # 黑帧
            FrameSample(at_ms=200, mean_luma=100, phash="c"),
        ],
        audio_windows=[
            AudioWindow(
                at_ms=0,
                duration_ms=45000,
                lufs=-14.0,
                true_peak_dbtp=-3.0,
                has_voice=False,
                tail_amplitude=0.001,
            )
        ],
        measured_duration_ms=45000,
        broll_duration_ms=10000,
        total_video_duration_ms=45000,
    )
    result = fake.analyze(MediaAnalysisRequest(resolved_path="/staging/final.mp4"))
    input_data = MediaSampleInput(
        video_frames=[
            VideoFrameSample(at_ms=s.at_ms, mean_luma=s.mean_luma, phash=s.phash)
            for s in result.frame_samples
        ],
        audio_windows=[
            AudioWindowSample(
                at_ms=w.at_ms,
                duration_ms=w.duration_ms,
                lufs=w.lufs,
                true_peak_dbtp=w.true_peak_dbtp,
                has_voice=w.has_voice,
                tail_amplitude=w.tail_amplitude,
            )
            for w in result.audio_windows
        ],
        broll_duration_ms=result.broll_duration_ms,
        total_video_duration_ms=result.total_video_duration_ms,
        measured_duration_ms=result.measured_duration_ms,
    )
    report = aggregate_qa_report(
        input_data, report_id="r", timeline_id="tl", timeline_duration_ms=45000, created_at=_T0
    )
    assert report.pass_or_block is False
    assert validate_publish_gate(report.findings) is PublishGate.BLOCK
