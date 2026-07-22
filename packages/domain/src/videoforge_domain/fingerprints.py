"""指纹原语（docs/modules/41 §5）。纯函数，无 I/O、无框架，逐位可重放。

- text_simhash：文本内容指纹（SimHash），char 3-gram + blake2b + 位投票，中英皆稳；
  同脚本不同画面可靠聚合，轻微改写仍近邻。
- dhash_from_gray：帧感知哈希（difference hash），从灰度矩阵逐行比较相邻像素；
  抗转码/轻微缩放（真实抽帧在 media-core 用 ffmpeg args-array 完成）。
- hamming / phash_sequence_similarity：比较原语。序列相似度用双向近邻命中率，
  鲁棒于不同帧率/轻裁剪（多数帧仍能找到近似帧）。

真实媒体的抽帧/音频指纹是 I/O，落在 media-core / 外部工具；本模块只做纯算法。
"""

from __future__ import annotations

import hashlib

_SIMHASH_BITS = 64


def _text_tokens(text: str) -> list[str]:
    # 归一化（小写、折叠空白）后取 char 3-gram：对中英混排与轻微改写都稳
    norm = " ".join(text.lower().split())
    if not norm:
        return []
    if len(norm) < 3:
        return [norm]
    return [norm[i : i + 3] for i in range(len(norm) - 2)]


def _token_hash(token: str) -> int:
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")


def text_simhash(text: str, *, bits: int = _SIMHASH_BITS) -> int:
    """文本 → SimHash（默认 64 位）。同/近内容汉明距离小。空文本返回 0。"""
    votes = [0] * bits
    for token in _text_tokens(text):
        h = _token_hash(token)
        for b in range(bits):
            votes[b] += 1 if (h >> b) & 1 else -1
    out = 0
    for b in range(bits):
        if votes[b] > 0:
            out |= 1 << b
    return out


def dhash_from_gray(width: int, height: int, pixels: bytes, *, hash_size: int = 8) -> int:
    """灰度矩阵 → difference hash（默认 64 位）。

    期望帧被缩放到 (hash_size+1) x hash_size 灰度（如 9x8），逐行比较相邻像素：
    左 > 右 记 1。pixels 为逐行排列的单通道字节（长度 ≥ width*height）。

    局限（感知哈希通病）：均匀帧（纯黑/纯色）梯度全为 0 → 哈希趋 0，两个多为均匀帧的
    不同视频可能误判近似；由人审流程知晓，不在此层解决。
    """
    if hash_size < 1:
        raise ValueError("hash_size 必须 ≥ 1")
    if width < hash_size + 1 or height < hash_size:
        raise ValueError(f"帧尺寸不足：需 ≥ {hash_size + 1}x{hash_size}，得 {width}x{height}")
    if len(pixels) < width * height:
        raise ValueError(f"像素字节不足：需 {width * height}，得 {len(pixels)}")
    bits = 0
    for row in range(hash_size):
        base = row * width
        for col in range(hash_size):
            left = pixels[base + col]
            right = pixels[base + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    """两个哈希的汉明距离（异或后 popcount）。"""
    return (a ^ b).bit_count()


def hamming_similarity(a: int, b: int, *, bits: int = _SIMHASH_BITS) -> float:
    """1 - 汉明距离/位数，落在 [0, 1]。"""
    return 1.0 - hamming(a, b) / bits


def phash_sequence_similarity(
    seq_a: tuple[int, ...],
    seq_b: tuple[int, ...],
    *,
    frame_max_hamming: int,
) -> float:
    """两个帧哈希序列的相似度 [0, 1]，与对齐/长度无关。

    双向近邻命中率的平均：A 中每帧在 B 里存在汉明距离 ≤ 阈值的近似帧即算命中。
    转码 → 逐帧近乎相同（高相似）；轻裁剪 → 多数帧仍命中；异内容 → 命中稀少。
    """
    if not seq_a or not seq_b:
        return 0.0

    def hit_rate(xs: tuple[int, ...], ys: tuple[int, ...]) -> float:
        hits = sum(1 for x in xs if any(hamming(x, y) <= frame_max_hamming for y in ys))
        return hits / len(xs)

    return (hit_rate(seq_a, seq_b) + hit_rate(seq_b, seq_a)) / 2.0
