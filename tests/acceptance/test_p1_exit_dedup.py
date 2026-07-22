"""P1 Exit 验收（去重）：同内容不同转码聚入同 duplicate group，来源仍独立。

54 §2 去重行：Given 同内容不同转码 / When 导入 / Then 同 duplicate group，来源仍独立。
纯 domain find_duplicate_groups 证明（真实 ffmpeg 端到端另见 media-core 集成测试）。
"""

from videoforge_domain import (
    AssetFingerprint,
    DuplicateLayer,
    find_duplicate_groups,
    text_simhash,
)

_VIDEO = (0x0F0F0F0F, 0x12345678, 0xAABBCCDD, 0x01020408, 0x13579BDF)


def test_same_content_different_transcode_same_group_sources_independent() -> None:
    transcoded = tuple(h ^ 0b11 for h in _VIDEO)  # 逐帧低汉明扰动（模拟转码）
    fps = [
        AssetFingerprint("dy-src", "sha_douyin", video_phashes=_VIDEO),
        AssetFingerprint("tt-src", "sha_tiktok", video_phashes=transcoded),
        AssetFingerprint("other", "sha_other", video_phashes=(0xFFFFFFFF, 0x0, 0x5555, 0xF0F0)),
    ]
    before = list(fps)
    groups = find_duplicate_groups(fps)

    assert len(groups) == 1
    assert set(groups[0].member_asset_ids) == {"dy-src", "tt-src"}  # 两转码同组
    assert DuplicateLayer.VIDEO in groups[0].layers
    # 来源仍独立：引擎不删、不改输入，三条来源记录都在
    assert fps == before
    assert len(fps) == 3


def test_multilayer_dedup_file_video_text() -> None:
    # 三层证据都能建组：文件精确 / 视频转码 / 同脚本异画面
    script = "三分钟看懂 AI 剪辑工作流"
    fps = [
        AssetFingerprint("a", "same_sha"),
        AssetFingerprint("b", "same_sha"),  # FILE
        AssetFingerprint("c", "sha_c", video_phashes=_VIDEO),
        AssetFingerprint("d", "sha_d", video_phashes=tuple(h ^ 1 for h in _VIDEO)),  # VIDEO
        AssetFingerprint("e", "sha_e", text_simhash=text_simhash(script)),
        AssetFingerprint("f", "sha_f", text_simhash=text_simhash(script + "！")),  # TEXT
    ]
    groups = find_duplicate_groups(fps)
    layers = {layer for g in groups for layer in g.layers}
    assert {DuplicateLayer.FILE, DuplicateLayer.VIDEO, DuplicateLayer.TEXT} <= layers
    assert len(groups) == 3  # 三对各成一组
