"""时间线交换 Exporter：Unconfigured 诚实 + OtioDictExporter 注入 domain 映射（分层保持）。"""

from datetime import UTC, datetime

from videoforge_contracts import (
    CreativeTimeline,
    RationalTime,
    RationalTimeRange,
    Segment,
    Track,
    TrackKind,
)
from videoforge_domain import to_otio_mapping  # 端到端注入用；provider-sdk src 本身不引 domain
from videoforge_provider_sdk import (
    OtioDictExporter,
    TimelineExporter,
    TimelineExporterStatus,
    TimelineExportRequest,
    UnconfiguredTimelineExporter,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _rt(v: int) -> RationalTime:
    return RationalTime(value=v, rate=30)


def _timeline() -> CreativeTimeline:
    v1 = Track(
        id="v1",
        kind=TrackKind.V1_PRIMARY_VIDEO,
        segments=[
            Segment(
                id="v1-s0",
                time_range=RationalTimeRange(start=_rt(0), duration=_rt(150)),
                source_ref="asset-a",
                semantic_role="HOOK",
            ),
        ],
    )
    a0 = Track(
        id="a0",
        kind=TrackKind.A0_ORIGINAL,
        segments=[
            Segment(id="a0-s0", time_range=RationalTimeRange(start=_rt(0), duration=_rt(150))),
        ],
    )
    return CreativeTimeline(id="tl", rate=30, duration=_rt(150), tracks=[v1, a0], created_at=_T0)


def test_protocol_conformance() -> None:
    assert isinstance(OtioDictExporter(to_otio_mapping), TimelineExporter)
    assert isinstance(UnconfiguredTimelineExporter(), TimelineExporter)


def test_unconfigured_is_honest() -> None:
    prov = UnconfiguredTimelineExporter(target_format="fcpxml")
    result = prov.export(TimelineExportRequest(timeline=_timeline(), target_format="fcpxml"))
    assert result.status is TimelineExporterStatus.UNCONFIGURED
    assert result.payload == {}
    assert result.error_code is not None
    assert prov.health_check().status is TimelineExporterStatus.UNCONFIGURED


def test_otio_dict_exporter_produces_valid_mapping() -> None:
    # 端到端：CreativeTimeline → OtioDictExporter（注入 domain 映射）→ OTIO dict
    exporter = OtioDictExporter(to_otio_mapping)
    result = exporter.export(TimelineExportRequest(timeline=_timeline()))
    assert result.ok and result.format == "otio"
    payload = result.payload
    assert payload["OTIO_SCHEMA"] == "Timeline.1"
    tracks = payload["tracks"]["children"]
    assert len(tracks) == 2
    assert tracks[0]["kind"] == "Video"
    # 扩展字段落 metadata.videoforge 未丢失
    assert tracks[0]["children"][0]["metadata"]["videoforge"]["source_ref"] == "asset-a"


def test_exporter_uses_injected_mapper_only() -> None:
    # 注入的映射函数被调用一次 —— 证实端口不依赖内建 domain 引用
    calls: list[CreativeTimeline] = []

    def spy_mapper(tl: CreativeTimeline) -> dict:
        calls.append(tl)
        return {"OTIO_SCHEMA": "Timeline.1", "spy": True}

    exporter = OtioDictExporter(spy_mapper, name="spy")
    result = exporter.export(TimelineExportRequest(timeline=_timeline()))
    assert result.ok and result.payload == {"OTIO_SCHEMA": "Timeline.1", "spy": True}
    assert len(calls) == 1
