"""NLE 交换 Exporter：OTIO/FCPXML 真写文件、剪映/CapCut fallback 包、白名单强制、单失败不阻断。"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from videoforge_contracts import (
    CreativeTimeline,
    ExporterKind,
    ExporterStatus,
    RationalTime,
    RationalTimeRange,
    Segment,
    Track,
    TrackKind,
)
from videoforge_domain import (
    UnsafeInputPath,
    export_all,
    from_otio_mapping,
    read_otio_file,
    write_capcut_package,
    write_fcpxml_file,
    write_jianying_package,
    write_otio_file,
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
                id="v0",
                time_range=RationalTimeRange(start=_rt(0), duration=_rt(150)),
                source_ref="asset-a",
                semantic_role="HOOK",
                script_sentence_id="s-0",
                speaker_id="host",
                provenance_ref="ra-1",
            ),
        ],
    )
    a0 = Track(
        id="a0",
        kind=TrackKind.A0_ORIGINAL,
        segments=[
            Segment(id="a0-0", time_range=RationalTimeRange(start=_rt(0), duration=_rt(150))),
        ],
    )
    return CreativeTimeline(
        id="tl-e2e", rate=30, duration=_rt(150), tracks=[v1, a0], created_at=_T0
    )


# —— OTIO 写文件 + 与 VF-306 dict 语义一致 ——


def test_write_otio_file_produces_valid_json_and_roundtrips(tmp_path: Path) -> None:
    out = tmp_path / "timeline.otio"
    entry = write_otio_file(_timeline(), str(out), allowed_roots=(str(tmp_path),))
    assert entry.status is ExporterStatus.OK
    assert entry.output_path == str(out)
    assert out.exists() and entry.bytes_written == len(out.read_bytes())
    # 读回是合法 JSON，OTIO_SCHEMA 顶层
    payload = read_otio_file(str(out))
    assert payload["OTIO_SCHEMA"] == "Timeline.1"
    # 与 VF-306 from_otio_mapping 往返一致（扩展字段全保留）
    restored = from_otio_mapping(payload, created_at=_T0)
    assert restored.rate == 30 and restored.duration.value == 150
    r_seg = restored.tracks[0].segments[0]
    assert r_seg.source_ref == "asset-a" and r_seg.semantic_role == "HOOK"


def test_write_otio_file_rejects_dotdot_traversal(tmp_path: Path) -> None:
    # `..` traversal 越出白名单，UnsafeInputPath（不降级为 FAILED，安全违规硬抛）
    with pytest.raises(UnsafeInputPath):
        write_otio_file(_timeline(), f"{tmp_path}/../../etc/passwd", allowed_roots=(str(tmp_path),))


def test_write_otio_file_rejects_outside_whitelist(tmp_path: Path) -> None:
    with pytest.raises(UnsafeInputPath):
        write_otio_file(_timeline(), "/etc/passwd", allowed_roots=(str(tmp_path),))


# —— FCPXML ——


def test_write_fcpxml_file_produces_parseable_xml(tmp_path: Path) -> None:
    import xml.etree.ElementTree as ET

    out = tmp_path / "timeline.fcpxml"
    entry = write_fcpxml_file(_timeline(), str(out), allowed_roots=(str(tmp_path),))
    assert entry.status is ExporterStatus.OK
    root = ET.parse(str(out)).getroot()
    assert root.tag == "fcpxml" and root.attrib["version"] == "1.10"
    # 每 segment 落一个 <clip>
    clips = root.findall(".//clip")
    assert len(clips) == 2  # v1 + a0 各一


def test_write_fcpxml_file_extension_fields_in_note(tmp_path: Path) -> None:
    out = tmp_path / "timeline.fcpxml"
    write_fcpxml_file(_timeline(), str(out), allowed_roots=(str(tmp_path),))
    import xml.etree.ElementTree as ET

    root = ET.parse(str(out)).getroot()
    notes = [json.loads(n.text) for n in root.findall(".//note") if n.text]
    v1_note = next(n for n in notes if n["source_ref"] == "asset-a")
    assert v1_note["semantic_role"] == "HOOK"
    assert v1_note["script_sentence_id"] == "s-0"
    assert v1_note["track_kind"] == "V1_PRIMARY_VIDEO"


def test_write_fcpxml_note_carries_all_nine_extension_fields(tmp_path: Path) -> None:
    # 回归：verifier 揭示原 FCPXML note 只带 6/9 字段，effects/crop_path/localization 静默丢失
    import xml.etree.ElementTree as ET

    from videoforge_contracts import LocalizationPolicy, SegmentEffect

    v1 = Track(
        id="v1",
        kind=TrackKind.V1_PRIMARY_VIDEO,
        segments=[
            Segment(
                id="v0",
                time_range=RationalTimeRange(start=_rt(0), duration=_rt(150)),
                source_ref="asset-a",
                semantic_role="HOOK",
                script_sentence_id="s-0",
                speaker_id="host",
                provenance_ref="ra-1",
                template_slot="slot-3",
                effects=[SegmentEffect(kind="fade_in", params={"duration_ms": "300"})],
                crop_path="crop-9x16-track1",
                localization=LocalizationPolicy(language="zh-CN", strategy="dub"),
            ),
        ],
    )
    tl = CreativeTimeline(id="tl", rate=30, duration=_rt(150), tracks=[v1], created_at=_T0)
    out = tmp_path / "timeline.fcpxml"
    write_fcpxml_file(tl, str(out), allowed_roots=(str(tmp_path),))
    root = ET.parse(str(out)).getroot()
    note = json.loads(root.find(".//note").text)
    # 全 9 字段 + track_kind
    for key in (
        "source_ref",
        "semantic_role",
        "script_sentence_id",
        "speaker_id",
        "provenance_ref",
        "template_slot",
        "effects",
        "crop_path",
        "localization",
    ):
        assert key in note, f"FCPXML note 缺 {key}"
    assert note["effects"][0]["kind"] == "fade_in"
    assert note["crop_path"] == "crop-9x16-track1"
    assert note["localization"]["language"] == "zh-CN"


def test_output_path_metachars_rejected_before_write(tmp_path: Path) -> None:
    # 回归：元字符路径必须写盘前拒（不能报告 FAILED 却已落盘）
    metachar_path = str(tmp_path / "evil$(id).otio")
    with pytest.raises(UnsafeInputPath, match="shell 元字符"):
        write_otio_file(_timeline(), metachar_path, allowed_roots=(str(tmp_path),))
    # 磁盘上不应留下这个文件
    assert not Path(metachar_path).exists()


# —— JianYing / CapCut fallback ——


def test_write_jianying_package_produces_partial_with_readme(tmp_path: Path) -> None:
    out_dir = tmp_path / "jianying-package"
    entry = write_jianying_package(_timeline(), str(out_dir), allowed_roots=(str(tmp_path),))
    assert entry.status is ExporterStatus.PARTIAL
    assert entry.warnings and "剪映" in entry.warnings[0]
    assert (out_dir / "timeline.json").exists()
    assert (out_dir / "README.md").exists()
    # README 明确说明"发布链路已产出 MP4"（§10 底线）
    readme = (out_dir / "README.md").read_text(encoding="utf-8")
    assert "MP4 最终成品" in readme or "§10" in readme


def test_write_capcut_package_experimental_fallback(tmp_path: Path) -> None:
    out_dir = tmp_path / "capcut-package"
    entry = write_capcut_package(_timeline(), str(out_dir), allowed_roots=(str(tmp_path),))
    assert entry.status is ExporterStatus.PARTIAL
    assert "experimental" in (entry.tool_version or "")


# —— export_all 单失败不阻断 ——


def test_export_all_runs_multiple_exporters_independently(tmp_path: Path) -> None:
    plan = {
        ExporterKind.OTIO_FILE: str(tmp_path / "tl.otio"),
        ExporterKind.FCPXML: str(tmp_path / "tl.fcpxml"),
        ExporterKind.JIANYING: str(tmp_path / "jianying/"),
    }
    report = export_all(
        _timeline(),
        plan,
        allowed_roots=(str(tmp_path),),
        report_id="rep-0",
        created_at=_T0,
    )
    assert len(report.entries) == 3
    kinds = {e.kind for e in report.entries}
    assert kinds == {ExporterKind.OTIO_FILE, ExporterKind.FCPXML, ExporterKind.JIANYING}


def test_export_all_single_bad_path_does_not_block_others(tmp_path: Path) -> None:
    # OTIO 路径合法，FCPXML 路径越出白名单 → OTIO 应 OK，FCPXML 应 FAILED（不抛异常）
    plan = {
        ExporterKind.OTIO_FILE: str(tmp_path / "tl.otio"),
        ExporterKind.FCPXML: "/etc/passwd",
    }
    report = export_all(
        _timeline(),
        plan,
        allowed_roots=(str(tmp_path),),
        report_id="rep-0",
        created_at=_T0,
    )
    by_kind = {e.kind: e for e in report.entries}
    assert by_kind[ExporterKind.OTIO_FILE].status is ExporterStatus.OK  # 未被拖累
    assert by_kind[ExporterKind.FCPXML].status is ExporterStatus.FAILED
    assert any("越出白名单" in err for err in by_kind[ExporterKind.FCPXML].errors)


def test_export_all_empty_plan_yields_empty_report(tmp_path: Path) -> None:
    report = export_all(
        _timeline(), {}, allowed_roots=(str(tmp_path),), report_id="rep-0", created_at=_T0
    )
    assert report.entries == []
