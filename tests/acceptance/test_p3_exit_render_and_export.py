"""P3 Exit 验收 —— PROXY vs FINAL 切点差 <1 帧 + OTIO grep 结构 + 剪映失败不阻断（§12 4/6/7）。

§12 第 4 条：代理渲染与最终渲染的切点差 <1 帧 —— 同一 CreativeTimeline 在 PROXY/FINAL
两 stage 下的 trim/atrim 起止秒数必须完全一致（切点由 timeline 决定，不受编码参数影响）。
第 6 条：OTIO 文件可导入 DaVinci —— 此处以 grep 验证输出为合法 OTIO_SCHEMA JSON、含关键
字段（tracks/segments/rate/duration/扩展字段），DaVinci 客户端联合导入需人工在 55 冒烟。
第 7 条：剪映/CapCut Adapter 失败标记为"Adapter 限制"但不破坏 Project 批量导出。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from videoforge_contracts import (
    CreativeTimeline,
    ExporterKind,
    ExporterStatus,
    RationalTime,
    RationalTimeRange,
    RenderStage,
    RenderTargetKind,
    Segment,
    Track,
    TrackKind,
)
from videoforge_domain import (
    CompileConfig,
    compile_timeline,
    export_all,
    from_otio_mapping,
    read_otio_file,
    write_capcut_package,
    write_fcpxml_file,
    write_jianying_package,
    write_otio_file,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _rt(v: int, rate: int = 30) -> RationalTime:
    return RationalTime(value=v, rate=rate)


def _timeline_with_three_cuts() -> CreativeTimeline:
    """3 段视频 + 3 段音频的时间轴 —— 覆盖多切点 concat 场景。"""
    v_segs = [
        Segment(id="v0", time_range=RationalTimeRange(start=_rt(0), duration=_rt(90)),
                 source_ref="a", semantic_role="HOOK"),
        Segment(id="v1", time_range=RationalTimeRange(start=_rt(90), duration=_rt(150)),
                 source_ref="b", semantic_role="EVIDENCE"),
        Segment(id="v2", time_range=RationalTimeRange(start=_rt(240), duration=_rt(120)),
                 source_ref="a", semantic_role="CTA"),
    ]
    a_segs = [
        Segment(id="a0", time_range=RationalTimeRange(start=_rt(0), duration=_rt(90)),
                 source_ref="a"),
        Segment(id="a1", time_range=RationalTimeRange(start=_rt(90), duration=_rt(150)),
                 source_ref="b"),
        Segment(id="a2", time_range=RationalTimeRange(start=_rt(240), duration=_rt(120)),
                 source_ref="a"),
    ]
    return CreativeTimeline(
        id="tl-cuts", rate=30, duration=_rt(360),
        tracks=[
            Track(id="v1t", kind=TrackKind.V1_PRIMARY_VIDEO, segments=v_segs),
            Track(id="a0t", kind=TrackKind.A0_ORIGINAL, segments=a_segs),
        ],
        created_at=_T0,
    )


def _extract_trim_cuts(graph) -> list[tuple[str, str, str]]:
    """从 FilterGraph 里提取所有 trim/atrim 节点的 (filter, start, end) 三元组。"""
    return sorted(
        (n.filter, n.params["start"], n.params["end"])
        for n in graph.filter_complex.nodes
        if n.filter in ("trim", "atrim")
    )


# —— §12 第 4 条：PROXY vs FINAL 切点差 <1 帧（等于 0 帧）——

def test_proxy_and_final_share_identical_cut_points(tmp_path: Path) -> None:
    tl = _timeline_with_three_cuts()
    resolved = {"a": (str(tmp_path / "a.mp4"), "0" * 64),
                 "b": (str(tmp_path / "b.mp4"), "1" * 64)}
    # 两 stage 用同一 output_path 会互相覆盖 —— 只关心 filter_graph 切点
    proxy_graph = compile_timeline(
        tl, resolved,
        CompileConfig(output_path=str(tmp_path / "proxy.mp4"),
                       allowed_input_roots=(str(tmp_path),),
                       stage=RenderStage.PROXY, target=RenderTargetKind.MP4_H264),
        tool_version="ffmpeg-8.1.2",
    )
    final_graph = compile_timeline(
        tl, resolved,
        CompileConfig(output_path=str(tmp_path / "final.mp4"),
                       allowed_input_roots=(str(tmp_path),),
                       stage=RenderStage.FINAL, target=RenderTargetKind.MP4_H264),
        tool_version="ffmpeg-8.1.2",
    )

    proxy_cuts = _extract_trim_cuts(proxy_graph)
    final_cuts = _extract_trim_cuts(final_graph)
    assert proxy_cuts == final_cuts, \
        f"PROXY 与 FINAL 切点不一致 —— 差绝非 <1 帧\nPROXY={proxy_cuts}\nFINAL={final_cuts}"
    # 至少 3 视频 + 3 音频 trim 节点
    assert len(proxy_cuts) >= 6, f"未生成足够的 trim 节点，实际 {len(proxy_cuts)}"


def test_proxy_and_final_only_differ_in_codec_flags(tmp_path: Path) -> None:
    """两 stage 的 args 差异应仅位于 codec/preset 段 —— 输入 -i、-map 段完全一致。"""
    tl = _timeline_with_three_cuts()
    resolved = {"a": (str(tmp_path / "a.mp4"), "0" * 64),
                 "b": (str(tmp_path / "b.mp4"), "1" * 64)}
    proxy_args = compile_timeline(
        tl, resolved,
        CompileConfig(output_path=str(tmp_path / "proxy.mp4"),
                       allowed_input_roots=(str(tmp_path),), stage=RenderStage.PROXY),
        tool_version="ffmpeg-8.1.2",
    ).args
    final_args = compile_timeline(
        tl, resolved,
        CompileConfig(output_path=str(tmp_path / "final.mp4"),
                       allowed_input_roots=(str(tmp_path),), stage=RenderStage.FINAL),
        tool_version="ffmpeg-8.1.2",
    ).args
    # 提取 -i 到 -map 段（输入映射，与 stage 无关）
    def _input_map_slice(args: list[str]) -> list[str]:
        keep: list[str] = []
        i = 0
        while i < len(args):
            if args[i] == "-i" and i + 1 < len(args):
                keep.extend(args[i:i + 2])
                i += 2
            elif args[i] == "-map" and i + 1 < len(args):
                keep.extend(args[i:i + 2])
                i += 2
            else:
                i += 1
        return keep
    assert _input_map_slice(proxy_args) == _input_map_slice(final_args), \
        "输入映射段 PROXY/FINAL 不一致 —— 切点/映射被 stage 意外影响"
    # crf 应不同（PROXY 快编 vs FINAL 品质）
    assert "-crf" in proxy_args and "-crf" in final_args
    proxy_crf = proxy_args[proxy_args.index("-crf") + 1]
    final_crf = final_args[final_args.index("-crf") + 1]
    assert proxy_crf != final_crf, "PROXY 与 FINAL 的 crf 应不同"


# —— §12 第 6 条：OTIO 结构可被外部导入（grep 级）——

def test_otio_file_has_expected_structure_for_davinci_import(tmp_path: Path) -> None:
    """OTIO 文件应含 DaVinci 识别的必要字段：OTIO_SCHEMA/tracks/global_start_time/duration。"""
    tl = _timeline_with_three_cuts()
    out = tmp_path / "davinci.otio"
    entry = write_otio_file(tl, str(out), allowed_roots=(str(tmp_path),))
    assert entry.status is ExporterStatus.OK

    raw = out.read_text(encoding="utf-8")
    # 顶层 schema 版本
    assert '"OTIO_SCHEMA"' in raw and '"Timeline.1"' in raw
    # OTIO 关键节点：tracks(Stack) + children(Track) + Clip
    assert '"tracks"' in raw and '"children"' in raw
    assert '"Stack.1"' in raw and '"Track.1"' in raw and '"Clip.1"' in raw
    assert '"source_range"' in raw and '"TimeRange.1"' in raw
    # §12 第 6 条硬要求：DaVinci 需靠 media_reference 重连媒体
    assert '"media_reference"' in raw and '"ExternalReference.1"' in raw
    assert '"target_url"' in raw
    # v0 段的 source_ref="a" 应作为 target_url 落地
    payload = read_otio_file(str(out))
    v0_clip = payload["tracks"]["children"][0]["children"][0]
    assert v0_clip["media_reference"]["OTIO_SCHEMA"] == "ExternalReference.1"
    assert v0_clip["media_reference"]["target_url"] == "a"
    # 与 VF-306 dict 端往返一致
    payload = read_otio_file(str(out))
    restored = from_otio_mapping(payload, created_at=_T0)
    assert restored.duration.value == 360 and restored.rate == 30
    # 三段视频 + 三段音频扩展字段保留
    v_track = next(t for t in restored.tracks if t.kind is TrackKind.V1_PRIMARY_VIDEO)
    assert [s.source_ref for s in v_track.segments] == ["a", "b", "a"]
    assert [s.semantic_role for s in v_track.segments] == ["HOOK", "EVIDENCE", "CTA"]


# —— §12 第 7 条：剪映/CapCut 失败标记不破坏 Project 批量导出 ——

def test_jianying_capcut_return_partial_but_do_not_break_batch(tmp_path: Path) -> None:
    tl = _timeline_with_three_cuts()
    plan = {
        ExporterKind.OTIO_FILE: str(tmp_path / "t.otio"),
        ExporterKind.FCPXML: str(tmp_path / "t.fcpxml"),
        ExporterKind.JIANYING: str(tmp_path / "jy/"),
        ExporterKind.CAPCUT: str(tmp_path / "cc/"),
    }
    report = export_all(tl, plan, allowed_roots=(str(tmp_path),),
                          report_id="rep-p3exit", created_at=_T0)
    by_kind = {e.kind: e for e in report.entries}
    # OTIO/FCPXML 正常
    assert by_kind[ExporterKind.OTIO_FILE].status is ExporterStatus.OK
    assert by_kind[ExporterKind.FCPXML].status is ExporterStatus.OK
    # 剪映/CapCut 只有 PARTIAL —— 属"Adapter 限制"，不会把整体 export_all 拉挂
    assert by_kind[ExporterKind.JIANYING].status is ExporterStatus.PARTIAL
    assert by_kind[ExporterKind.CAPCUT].status is ExporterStatus.PARTIAL
    # 其它 exporter 未受连累
    assert by_kind[ExporterKind.OTIO_FILE].output_path == plan[ExporterKind.OTIO_FILE]


def test_export_all_single_hard_failure_isolates_but_batch_continues(tmp_path: Path) -> None:
    """§12：一个 Adapter 硬失败（越白名单）标记 FAILED，不影响其它 Exporter 完成。"""
    tl = _timeline_with_three_cuts()
    plan = {
        ExporterKind.OTIO_FILE: str(tmp_path / "t.otio"),
        ExporterKind.FCPXML: "/etc/passwd",  # 硬失败：越白名单
        ExporterKind.JIANYING: str(tmp_path / "jy/"),
    }
    report = export_all(tl, plan, allowed_roots=(str(tmp_path),),
                          report_id="rep-fail", created_at=_T0)
    by_kind = {e.kind: e for e in report.entries}
    assert by_kind[ExporterKind.OTIO_FILE].status is ExporterStatus.OK  # 未受连累
    assert by_kind[ExporterKind.FCPXML].status is ExporterStatus.FAILED
    assert by_kind[ExporterKind.JIANYING].status is ExporterStatus.PARTIAL
    # 单点失败错误信息应清晰
    assert any("越出白名单" in err for err in by_kind[ExporterKind.FCPXML].errors)


# —— 冒烟：单独调用每个 exporter 都成功产文件（并留下"发布链路以 MP4 为准"提示）——

def test_all_four_exporters_produce_expected_artifacts(tmp_path: Path) -> None:
    tl = _timeline_with_three_cuts()
    otio_out = tmp_path / "t.otio"
    fcp_out = tmp_path / "t.fcpxml"
    jy_dir = tmp_path / "jy"
    cc_dir = tmp_path / "cc"
    roots = (str(tmp_path),)
    ok = ExporterStatus.OK
    partial = ExporterStatus.PARTIAL
    assert write_otio_file(tl, str(otio_out), allowed_roots=roots).status is ok
    assert write_fcpxml_file(tl, str(fcp_out), allowed_roots=roots).status is ok
    assert write_jianying_package(tl, str(jy_dir), allowed_roots=roots).status is partial
    assert write_capcut_package(tl, str(cc_dir), allowed_roots=roots).status is partial

    # 4 个产物真存在
    assert otio_out.exists() and fcp_out.exists()
    assert (jy_dir / "timeline.json").exists() and (jy_dir / "README.md").exists()
    assert (cc_dir / "timeline.json").exists() and (cc_dir / "README.md").exists()
    # OTIO 可解为合法 JSON
    json.loads(otio_out.read_text(encoding="utf-8"))
