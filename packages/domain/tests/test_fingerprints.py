"""指纹原语：simhash 中英稳、dhash 差分、汉明、序列相似度鲁棒于转码/裁剪。"""

from videoforge_domain import (
    dhash_from_gray,
    hamming,
    hamming_similarity,
    phash_sequence_similarity,
    text_simhash,
)


def test_text_simhash_deterministic_and_replayable() -> None:
    a = text_simhash("AI 工具三分钟拆解视频工作流")
    b = text_simhash("AI 工具三分钟拆解视频工作流")
    assert a == b  # 逐位可重放


def test_text_simhash_same_script_is_near() -> None:
    base = "三分钟看懂 AI 剪辑工作流，从下载到成片一条龙"
    tweaked = "三分钟看懂 AI 剪辑工作流，从下载到成片一条龙！"  # 轻微改写
    different = "今天聊聊咖啡烘焙的火候与风味曲线"
    assert hamming(text_simhash(base), text_simhash(tweaked)) <= 6  # 同稿近邻（实测约 5 位）
    assert hamming(text_simhash(base), text_simhash(different)) > 10  # 异稿远


def test_text_simhash_empty_is_zero() -> None:
    assert text_simhash("") == 0
    assert text_simhash("   ") == 0


def test_dhash_from_gray_detects_gradient_direction() -> None:
    # 9x8 灰度，每行左小右大 → 每个相邻比较都是 left<right → 全 0 位
    ascending = bytes([col * 28 for _row in range(8) for col in range(9)])
    assert dhash_from_gray(9, 8, ascending) == 0
    # 每行左大右小 → 全 1 位（64 个 1）
    descending = bytes([(8 - col) * 28 for _row in range(8) for col in range(9)])
    assert bin(dhash_from_gray(9, 8, descending)).count("1") == 64


def test_dhash_rejects_undersized_frame() -> None:
    import pytest

    with pytest.raises(ValueError):
        dhash_from_gray(4, 4, bytes(16))


def test_hamming_and_similarity() -> None:
    assert hamming(0b1010, 0b1000) == 1
    assert hamming(0, 0) == 0
    assert hamming_similarity(0, 0) == 1.0
    assert hamming_similarity(0, (1 << 64) - 1) == 0.0


def test_sequence_similarity_transcode_high_different_low() -> None:
    original = (0x0F0F0F0F, 0x12345678, 0xAABBCCDD, 0x01020408)
    # 转码：每帧翻几位（低汉明距离）→ 高相似
    transcoded = tuple(h ^ 0b101 for h in original)
    assert phash_sequence_similarity(original, transcoded, frame_max_hamming=6) == 1.0
    # 完全不同的序列 → 低相似
    unrelated = (0xFFFFFFFF, 0x00000000, 0x55555555, 0xF0F0F0F0)
    assert phash_sequence_similarity(original, unrelated, frame_max_hamming=6) < 0.5


def test_sequence_similarity_light_trim_still_high() -> None:
    original = (0x0F0F0F0F, 0x12345678, 0xAABBCCDD, 0x01020408, 0x13579BDF)
    trimmed = original[1:]  # 掐头，多数帧仍在
    assert phash_sequence_similarity(original, trimmed, frame_max_hamming=4) >= 0.8


def test_sequence_similarity_empty_is_zero() -> None:
    assert phash_sequence_similarity((), (1, 2), frame_max_hamming=4) == 0.0
