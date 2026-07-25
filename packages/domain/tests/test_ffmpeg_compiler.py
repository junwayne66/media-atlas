"""FFmpeg 编译器：安全 argv + 路径白名单 + Filter Graph DAG + 复现 cache + serialize。"""

from datetime import UTC, datetime

import pytest

from videoforge_contracts import (
    CreativeTimeline,
    FilterGraph,
    FilterNode,
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
    UnsafeInputPath,
    build_render_manifest,
    compile_timeline,
    render_manifest_cache_key,
    serialize_filter_complex,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)
_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _rt(v: int, rate: int = 30) -> RationalTime:
    return RationalTime(value=v, rate=rate)


def _seg(sid: str, start: int, dur: int, source: str | None = None) -> Segment:
    return Segment(
        id=sid, time_range=RationalTimeRange(start=_rt(start), duration=_rt(dur)), source_ref=source
    )


def _timeline(
    video_segs: list[Segment],
    audio_segs: list[Segment],
    duration: int = 150,
) -> CreativeTimeline:
    v1 = Track(id="v1", kind=TrackKind.V1_PRIMARY_VIDEO, segments=video_segs)
    a0 = Track(id="a0", kind=TrackKind.A0_ORIGINAL, segments=audio_segs)
    return CreativeTimeline(
        id="tl", rate=30, duration=_rt(duration), tracks=[v1, a0], created_at=_T0
    )


def _config(**over) -> CompileConfig:
    base = {"output_path": "/staging/out/final.mp4", "allowed_input_roots": ("/staging",)}
    base.update(over)
    return CompileConfig(**base)


# —— 编译基本 ——


def test_compile_single_segment_produces_safe_argv() -> None:
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    rg = compile_timeline(
        tl, {"asset-a": ("/staging/source.mp4", _SHA_A)}, _config(), tool_version="ffmpeg-8.1.2"
    )
    assert rg.args[0] == "ffmpeg"
    # 无 shell 元字符（合同层已强制，此处再断一遍以文档化"absolutely no shell"）
    for token in rg.args:
        assert not any(c in ";|&<>`$\"'\n\r\t\\" for c in token)
    # -i 后跟绝对路径
    idx_i = rg.args.index("-i")
    assert rg.args[idx_i + 1] == "/staging/source.mp4"
    # 输出路径在最后
    assert rg.args[-1] == "/staging/out/final.mp4"
    assert rg.output_path == "/staging/out/final.mp4"
    assert rg.target is RenderTargetKind.MP4_H264
    assert rg.tool_version == "ffmpeg-8.1.2"


def test_compile_two_video_segments_uses_concat() -> None:
    tl = _timeline(
        [_seg("v0", 0, 60, "asset-a"), _seg("v1", 60, 90, "asset-b")],
        [_seg("a0", 0, 150, "asset-a")],
    )
    rg = compile_timeline(
        tl,
        {"asset-a": ("/staging/a.mp4", _SHA_A), "asset-b": ("/staging/b.mp4", _SHA_B)},
        _config(),
        tool_version="ffmpeg-8.1.2",
    )
    # 两段视频 → concat 节点
    concat_nodes = [n for n in rg.filter_complex.nodes if n.filter == "concat"]
    assert any(n.params.get("v") == "1" for n in concat_nodes)
    # 两个 -i
    assert rg.args.count("-i") == 2


def test_compile_deduplicates_source_refs_across_tracks() -> None:
    # V1 与 A0 都引用 asset-a，只应产生 1 个 -i
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    rg = compile_timeline(
        tl, {"asset-a": ("/staging/source.mp4", _SHA_A)}, _config(), tool_version="ffmpeg-8.1.2"
    )
    assert rg.args.count("-i") == 1
    assert len(rg.inputs) == 1


# —— 安全：白名单强制 ——


def test_compile_rejects_input_path_outside_whitelist() -> None:
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    # asset-a 解析到 /etc/passwd —— 越出 /staging 白名单
    with pytest.raises(UnsafeInputPath, match="越出白名单"):
        compile_timeline(
            tl, {"asset-a": ("/etc/passwd", _SHA_A)}, _config(), tool_version="ffmpeg-8.1.2"
        )


def test_compile_rejects_output_path_outside_whitelist() -> None:
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    with pytest.raises(UnsafeInputPath, match="output_path"):
        compile_timeline(
            tl,
            {"asset-a": ("/staging/source.mp4", _SHA_A)},
            _config(output_path="/tmp/attack.mp4"),  # /tmp 不在白名单
            tool_version="ffmpeg-8.1.2",
        )


def test_compile_rejects_relative_path() -> None:
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    with pytest.raises(UnsafeInputPath):
        compile_timeline(
            tl, {"asset-a": ("relative/source.mp4", _SHA_A)}, _config(), tool_version="ffmpeg-8.1.2"
        )


def test_compile_rejects_shell_injection_attempt_in_path() -> None:
    # 合同层验证器堵这类 —— 参数含 shell 元字符即被拒。ValidationError 或 UnsafeInputPath 都算合规。
    from pydantic import ValidationError

    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    with pytest.raises((ValidationError, UnsafeInputPath)):
        compile_timeline(
            tl,
            {"asset-a": ("/staging/$(rm -rf ~).mp4", _SHA_A)},
            _config(),
            tool_version="ffmpeg-8.1.2",
        )


def test_compile_rejects_dotdot_traversal_in_input_path() -> None:
    # 安全回归：verifier 揭示 PurePath.relative_to 是纯词法比较，不折叠 `..`。
    # `/staging/../../etc/passwd` 实际是 `/etc/passwd`，越出白名单。
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    for traversal in [
        "/staging/../../etc/passwd",
        "/staging/../etc/passwd",
        "/staging/a/../../etc/shadow",
        "/staging/./../../root/.ssh/id_rsa",
    ]:
        with pytest.raises(UnsafeInputPath, match="越出白名单"):
            compile_timeline(
                tl, {"asset-a": (traversal, _SHA_A)}, _config(), tool_version="ffmpeg-8.1.2"
            )


def test_compile_rejects_dotdot_traversal_in_output_path() -> None:
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    with pytest.raises(UnsafeInputPath, match="output_path"):
        compile_timeline(
            tl,
            {"asset-a": ("/staging/source.mp4", _SHA_A)},
            _config(output_path="/staging/../../tmp/evil.mp4"),
            tool_version="ffmpeg-8.1.2",
        )


def test_compile_accepts_dot_and_normal_subpaths() -> None:
    # 归一化不应误伤：`.` 段与深层子目录都能通过
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    rg = compile_timeline(
        tl,
        {"asset-a": ("/staging/./nested/source.mp4", _SHA_A)},
        _config(),
        tool_version="ffmpeg-8.1.2",
    )
    assert rg.inputs[0].resolved_path == "/staging/./nested/source.mp4"


def test_compile_rejects_missing_source_ref_resolution() -> None:
    tl = _timeline([_seg("v0", 0, 150, "asset-missing")], [_seg("a0", 0, 150, "asset-a")])
    with pytest.raises(UnsafeInputPath, match="未在 resolved_inputs 中解析"):
        compile_timeline(
            tl, {"asset-a": ("/staging/source.mp4", _SHA_A)}, _config(), tool_version="ffmpeg-8.1.2"
        )


# —— cache key 复现 ——


def test_render_manifest_cache_key_reproducible() -> None:
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    rg = compile_timeline(
        tl, {"asset-a": ("/staging/source.mp4", _SHA_A)}, _config(), tool_version="ffmpeg-8.1.2"
    )
    m = build_render_manifest(
        tl,
        rg,
        manifest_id="m",
        stage=RenderStage.FINAL,
        created_at=_T0,
        tool_version="ffmpeg-8.1.2",
    )
    k1 = render_manifest_cache_key(m)
    k2 = render_manifest_cache_key(m)
    assert k1 == k2 and len(k1) == 64  # sha256


def test_render_manifest_cache_key_differs_on_input_change() -> None:
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    rg1 = compile_timeline(
        tl, {"asset-a": ("/staging/source.mp4", _SHA_A)}, _config(), tool_version="ffmpeg-8.1.2"
    )
    rg2 = compile_timeline(
        tl,
        {"asset-a": ("/staging/source.mp4", _SHA_B)},  # 不同 sha
        _config(),
        tool_version="ffmpeg-8.1.2",
    )
    m1 = build_render_manifest(
        tl,
        rg1,
        manifest_id="m",
        stage=RenderStage.FINAL,
        created_at=_T0,
        tool_version="ffmpeg-8.1.2",
    )
    m2 = build_render_manifest(
        tl,
        rg2,
        manifest_id="m",
        stage=RenderStage.FINAL,
        created_at=_T0,
        tool_version="ffmpeg-8.1.2",
    )
    assert render_manifest_cache_key(m1) != render_manifest_cache_key(m2)


def test_render_manifest_cache_key_differs_on_tool_version() -> None:
    tl = _timeline([_seg("v0", 0, 150, "asset-a")], [_seg("a0", 0, 150, "asset-a")])
    rg = compile_timeline(
        tl, {"asset-a": ("/staging/source.mp4", _SHA_A)}, _config(), tool_version="ffmpeg-8.1.2"
    )
    m1 = build_render_manifest(
        tl,
        rg,
        manifest_id="m",
        stage=RenderStage.FINAL,
        created_at=_T0,
        tool_version="ffmpeg-8.1.2",
    )
    m2 = build_render_manifest(
        tl,
        rg,
        manifest_id="m",
        stage=RenderStage.FINAL,
        created_at=_T0,
        tool_version="ffmpeg-8.2.0",
    )
    assert render_manifest_cache_key(m1) != render_manifest_cache_key(m2)


# —— serialize FilterGraph → -filter_complex 字符串 ——


def test_serialize_filter_complex_single_node() -> None:
    fg = FilterGraph(
        nodes=[
            FilterNode(
                id="n0",
                filter="scale",
                params={"w": "1080", "h": "1920"},
                inputs=["0:v"],
                outputs=["v"],
            )
        ],
        sinks=["v"],
    )
    s = serialize_filter_complex(fg)
    assert s == "[0:v]scale=w=1080:h=1920[v]"


def test_serialize_filter_complex_multi_nodes_joined_with_semicolon() -> None:
    fg = FilterGraph(
        nodes=[
            FilterNode(
                id="n0",
                filter="trim",
                params={"start": "0", "end": "5"},
                inputs=["0:v"],
                outputs=["t"],
            ),
            FilterNode(
                id="n1",
                filter="setpts",
                params={"expr": "PTS-STARTPTS"},
                inputs=["t"],
                outputs=["v"],
            ),
        ],
        sinks=["v"],
    )
    s = serialize_filter_complex(fg)
    assert s == "[0:v]trim=start=0:end=5[t];[t]setpts=expr=PTS-STARTPTS[v]"


def test_serialize_filter_complex_no_params() -> None:
    fg = FilterGraph(
        nodes=[FilterNode(id="n0", filter="anull", inputs=["0:a"], outputs=["a"])],
        sinks=["a"],
    )
    assert serialize_filter_complex(fg) == "[0:a]anull[a]"
