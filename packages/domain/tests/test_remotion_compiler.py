"""Remotion 编译器：类型化 Props + 白名单 + cache key 复现 + 不触真实 Remotion。"""

from datetime import UTC, datetime

import pytest

from videoforge_contracts import (
    CreativeTimeline,
    RationalTime,
    RationalTimeRange,
    RemotionComposition,
    Segment,
    Track,
    TrackKind,
)
from videoforge_domain import (
    RemotionCompileConfig,
    UnsafeInputPath,
    build_remotion_render_manifest,
    compile_timeline_to_remotion,
    remotion_manifest_cache_key,
    serialize_props,
)

_T0 = datetime(2026, 7, 23, tzinfo=UTC)


def _rt(v: int, rate: int = 30) -> RationalTime:
    return RationalTime(value=v, rate=rate)


def _seg(sid: str, start: int, dur: int, **kw) -> Segment:
    return Segment(id=sid, time_range=RationalTimeRange(start=_rt(start), duration=_rt(dur)), **kw)


def _timeline() -> CreativeTimeline:
    v4 = Track(
        id="v4",
        kind=TrackKind.V4_CAPTIONS,
        segments=[
            _seg("cap0", 0, 45, script_sentence_id="s-0", speaker_id="host"),
            _seg("cap1", 45, 90, script_sentence_id="s-1"),
        ],
    )
    v1 = Track(
        id="v1",
        kind=TrackKind.V1_PRIMARY_VIDEO,
        segments=[_seg("v0", 0, 150, source_ref="asset-a")],
    )
    a0 = Track(id="a0", kind=TrackKind.A0_ORIGINAL, segments=[_seg("a0-0", 0, 150)])
    return CreativeTimeline(
        id="tl", rate=30, duration=_rt(150), tracks=[v1, v4, a0], created_at=_T0
    )


def _config(**over) -> RemotionCompileConfig:
    base = {
        "entry_component_path": "/staging/remotion/Root.tsx",
        "output_path": "/staging/out/captions.mp4",
        "allowed_input_roots": ("/staging",),
        "composition": RemotionComposition.CAPTIONS,
    }
    base.update(over)
    return RemotionCompileConfig(**base)


# —— 编译 ——


def test_compile_captions_composition_produces_typed_props() -> None:
    req = compile_timeline_to_remotion(
        _timeline(), _config(), request_id="req-0", tool_version="remotion-4.0.240"
    )
    assert req.composition is RemotionComposition.CAPTIONS
    prop_map = {p.key: p.value for p in req.props}
    assert prop_map["composition"] == "CAPTIONS"
    assert prop_map["fps"] == 30
    # captions 是有序列表，每条含 start_ms/end_ms
    caps = prop_map["captions"]
    assert len(caps) == 2
    assert caps[0]["segment_id"] == "cap0"
    assert caps[0]["start_ms"] == 0 and caps[0]["end_ms"] == 1500  # 45 帧 / 30 fps
    assert caps[0]["script_sentence_id"] == "s-0"
    assert caps[0]["speaker_id"] == "host"


def test_compile_info_card_composition_skips_captions() -> None:
    # INFO_CARD 组件不需要 CAPTIONS 轨的 props
    tl = _timeline()
    # 加一个 V3 info card 轨
    tl_with_info = tl.model_copy(
        update={
            "tracks": [
                *tl.tracks,
                Track(
                    id="v3",
                    kind=TrackKind.V3_INFO_CARDS,
                    segments=[_seg("card0", 0, 60, template_slot="stat-block")],
                ),
            ],
        }
    )
    req = compile_timeline_to_remotion(
        tl_with_info,
        _config(composition=RemotionComposition.INFO_CARD),
        request_id="req-1",
        tool_version="remotion-4.0.240",
    )
    prop_map = {p.key: p.value for p in req.props}
    assert "info_cards" in prop_map
    assert prop_map["info_cards"][0]["template_slot"] == "stat-block"
    assert "captions" not in prop_map  # composition 不匹配即不包含


# —— 安全：白名单强制（复用 VF-307 段级归一化）——


def test_compile_rejects_entry_path_outside_whitelist() -> None:
    with pytest.raises(UnsafeInputPath, match="entry_component_path"):
        compile_timeline_to_remotion(
            _timeline(),
            _config(entry_component_path="/etc/passwd"),
            request_id="req",
            tool_version="remotion-4.0.240",
        )


def test_compile_rejects_output_path_outside_whitelist() -> None:
    with pytest.raises(UnsafeInputPath, match="output_path"):
        compile_timeline_to_remotion(
            _timeline(),
            _config(output_path="/tmp/attack.mp4"),
            request_id="req",
            tool_version="remotion-4.0.240",
        )


def test_compile_rejects_dotdot_traversal_in_entry_path() -> None:
    # 与 VF-307 一致的 .. traversal 防御
    with pytest.raises(UnsafeInputPath, match="entry_component_path"):
        compile_timeline_to_remotion(
            _timeline(),
            _config(entry_component_path="/staging/../../etc/passwd"),
            request_id="req",
            tool_version="remotion-4.0.240",
        )


# —— serialize_props / cache key 复现 ——


def test_serialize_props_deterministic() -> None:
    req = compile_timeline_to_remotion(
        _timeline(), _config(), request_id="req", tool_version="remotion-4.0.240"
    )
    a = serialize_props(req.props)
    b = serialize_props(req.props)
    assert a == b
    # sort_keys → 手动改 dict 序不影响输出
    assert '"captions"' in a and '"composition":"CAPTIONS"' in a


def test_remotion_cache_key_reproducible_and_sensitive() -> None:
    req = compile_timeline_to_remotion(
        _timeline(), _config(), request_id="req", tool_version="remotion-4.0.240"
    )
    m1 = build_remotion_render_manifest(
        req,
        manifest_id="m",
        created_at=_T0,
        tool_version="remotion-4.0.240",
        input_digests={"asset-a": "a" * 64},
    )
    k1 = remotion_manifest_cache_key(m1)
    assert k1 == remotion_manifest_cache_key(m1)  # 复现
    m2 = build_remotion_render_manifest(
        req,
        manifest_id="m",
        created_at=_T0,
        tool_version="remotion-4.0.241",  # 版本变
        input_digests={"asset-a": "a" * 64},
    )
    assert remotion_manifest_cache_key(m2) != k1


def test_remotion_cache_key_sensitive_to_props_change() -> None:
    tl = _timeline()
    req1 = compile_timeline_to_remotion(
        tl, _config(), request_id="req", tool_version="remotion-4.0.240"
    )
    # 改字幕文本（间接通过修改 timeline）应影响 cache key
    tl2 = tl.model_copy(
        update={
            "tracks": [
                t
                if t.id != "v4"
                else Track(
                    id="v4",
                    kind=TrackKind.V4_CAPTIONS,
                    segments=[
                        _seg("cap0", 0, 60, script_sentence_id="s-0"),  # 时长变化
                    ],
                )
                for t in tl.tracks
            ],
        }
    )
    req2 = compile_timeline_to_remotion(
        tl2, _config(), request_id="req", tool_version="remotion-4.0.240"
    )
    m1 = build_remotion_render_manifest(
        req1, manifest_id="m", created_at=_T0, tool_version="remotion-4.0.240"
    )
    m2 = build_remotion_render_manifest(
        req2, manifest_id="m", created_at=_T0, tool_version="remotion-4.0.240"
    )
    assert remotion_manifest_cache_key(m1) != remotion_manifest_cache_key(m2)
