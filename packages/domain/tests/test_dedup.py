"""去重引擎：分层匹配 → duplicate group；只建组不删来源；确定性可重放。"""

from videoforge_domain import (
    AssetFingerprint,
    DedupConfig,
    DuplicateLayer,
    find_duplicate_groups,
    text_simhash,
)

_VIDEO = (0x0F0F0F0F, 0x12345678, 0xAABBCCDD, 0x01020408)


def _fp(asset_id, sha, **over) -> AssetFingerprint:
    return AssetFingerprint(asset_id=asset_id, sha256=sha, **over)


def test_exact_file_duplicates_group_via_file_layer() -> None:
    fps = [
        _fp("a1", "sha_x"),
        _fp("a2", "sha_x"),  # 同一文件
        _fp("a3", "sha_y"),  # 无关
    ]
    groups = find_duplicate_groups(fps)
    assert len(groups) == 1
    g = groups[0]
    assert g.member_asset_ids == ("a1", "a2")
    assert DuplicateLayer.FILE in g.layers
    assert g.similarity == 1.0


def test_same_content_different_transcode_groups_via_video() -> None:
    # 验收 41 §13：同视频不同转码聚入同 duplicate group
    transcoded = tuple(h ^ 0b11 for h in _VIDEO)  # 逐帧低汉明扰动
    fps = [
        _fp("dy-1", "sha_a", video_phashes=_VIDEO),
        _fp("tt-1", "sha_b", video_phashes=transcoded),  # 不同文件、同内容
    ]
    groups = find_duplicate_groups(fps)
    assert len(groups) == 1
    assert set(groups[0].member_asset_ids) == {"dy-1", "tt-1"}
    assert DuplicateLayer.VIDEO in groups[0].layers
    assert groups[0].similarity >= 0.8


def test_different_content_not_grouped() -> None:
    other = (0xFFFFFFFF, 0x00000000, 0x55555555, 0xF0F0F0F0)
    fps = [
        _fp("a1", "sha_a", video_phashes=_VIDEO),
        _fp("a2", "sha_b", video_phashes=other),
    ]
    assert find_duplicate_groups(fps) == []  # 不同内容不成组


def test_same_script_different_video_groups_via_text() -> None:
    script = "三分钟看懂 AI 剪辑工作流，从下载到成片"
    fps = [
        _fp("a1", "sha_a", video_phashes=_VIDEO, text_simhash=text_simhash(script)),
        _fp("a2", "sha_b", video_phashes=(1, 2, 3), text_simhash=text_simhash(script + "！")),
    ]
    groups = find_duplicate_groups(fps)
    assert len(groups) == 1
    assert DuplicateLayer.TEXT in groups[0].layers


def test_audio_exact_match_groups_via_audio() -> None:
    fps = [
        _fp("a1", "sha_a", audio_fingerprint="chroma:abc123"),
        _fp("a2", "sha_b", audio_fingerprint="chroma:abc123"),
        _fp("a3", "sha_c", audio_fingerprint="chroma:zzz999"),
    ]
    groups = find_duplicate_groups(fps)
    assert len(groups) == 1
    assert groups[0].member_asset_ids == ("a1", "a2")
    assert DuplicateLayer.AUDIO in groups[0].layers


def test_transitive_grouping_connected_components() -> None:
    # a~b（视频）、b~c（文本）→ a,b,c 一组（连通分量）
    tc = tuple(h ^ 0b1 for h in _VIDEO)
    script = "同一段脚本内容用于连通性测试"
    fps = [
        _fp("a", "s1", video_phashes=_VIDEO, text_simhash=text_simhash("画面一")),
        _fp("b", "s2", video_phashes=tc, text_simhash=text_simhash(script)),
        _fp("c", "s3", video_phashes=(9, 9, 9), text_simhash=text_simhash(script)),
    ]
    groups = find_duplicate_groups(fps)
    assert len(groups) == 1
    assert set(groups[0].member_asset_ids) == {"a", "b", "c"}
    assert DuplicateLayer.VIDEO in groups[0].layers and DuplicateLayer.TEXT in groups[0].layers


def test_group_id_is_deterministic_and_replayable() -> None:
    fps = [_fp("a1", "sha_x"), _fp("a2", "sha_x")]
    g1 = find_duplicate_groups(fps)
    g2 = find_duplicate_groups(fps)
    assert g1[0].group_id == g2[0].group_id  # 同成员集合恒定 id
    assert g1[0].group_id.startswith("dg-")


def test_no_input_mutation_and_no_deletion() -> None:
    # 引擎不改输入、不删来源——只返回分组建议
    fps = [_fp("a1", "sha_x"), _fp("a2", "sha_x"), _fp("a3", "sha_y")]
    original = list(fps)
    find_duplicate_groups(fps)
    assert fps == original  # 输入未被改动
    assert len(fps) == 3  # 来源记录一条不少


def test_empty_text_simhash_does_not_false_group() -> None:
    # 空转录 text_simhash("")==0；两个空文本资产不得以 TEXT 层误聚（0 视为无文本）
    fps = [
        _fp("a1", "sha_a", text_simhash=text_simhash("")),
        _fp("a2", "sha_b", text_simhash=text_simhash("")),
    ]
    assert find_duplicate_groups(fps) == []


def test_singletons_not_returned_as_groups() -> None:
    fps = [_fp("a1", "sha_a"), _fp("a2", "sha_b"), _fp("a3", "sha_c")]
    assert find_duplicate_groups(fps) == []  # 无重复 → 无组


def test_config_threshold_controls_video_grouping() -> None:
    a = (0x0F0F0F0F, 0x12345678)
    b = tuple(h ^ 0xFF for h in a)  # 每帧 8 位差
    loose = DedupConfig(video_frame_max_hamming=16, video_seq_min_similarity=0.5)
    strict = DedupConfig(video_frame_max_hamming=2, video_seq_min_similarity=0.9)
    fps = [_fp("a1", "s1", video_phashes=a), _fp("a2", "s2", video_phashes=b)]
    assert len(find_duplicate_groups(fps, loose)) == 1  # 松阈值聚合
    assert find_duplicate_groups(fps, strict) == []  # 严阈值不聚
