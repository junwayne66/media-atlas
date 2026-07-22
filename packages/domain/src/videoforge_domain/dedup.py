"""去重引擎（docs/modules/41 §5/§13）。纯函数，逐位可重放。

分层匹配：文件（SHA-256 精确）/ 视频（pHash 序列相似）/ 文本（SimHash 汉明）/
音频（指纹精确）。命中即在并查集里连边，最终连通分量即 duplicate group。

铁律（README §4 / 41 §5）：**只建立 duplicate_group_id 和相似度，绝不删除任何来源记录。**
本引擎不改动输入、不产生删除动作，只返回分组建议。group_id 由成员集合确定性派生，可重放。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum

from videoforge_domain.fingerprints import hamming, phash_sequence_similarity

_SIMHASH_BITS = 64


class DuplicateLayer(StrEnum):
    FILE = "FILE"  # 完全相同文件（SHA-256）
    VIDEO = "VIDEO"  # 同内容不同转码/轻裁剪（pHash 序列）
    AUDIO = "AUDIO"  # 同音轨/搬运（音频指纹）
    TEXT = "TEXT"  # 同脚本不同画面（文本 SimHash）


@dataclass(frozen=True)
class AssetFingerprint:
    """一个来源资产的多层指纹。缺失层为 None/空——不参与该层匹配（null 非 0）。"""

    asset_id: str
    sha256: str
    video_phashes: tuple[int, ...] = ()
    audio_fingerprint: str | None = None
    text_simhash: int | None = None


@dataclass(frozen=True)
class DedupConfig:
    video_frame_max_hamming: int = 10  # 单帧 dHash 视为近似的最大汉明距离
    video_seq_min_similarity: float = 0.8  # 序列相似度阈值
    # 文本 SimHash 视为同稿的最大汉明距离。实测：单字/标点改写 ~4-5 位、异稿 ~31 位，
    # 8 位阈值区分度足够（同一视频的两次转录汉明近 0）
    text_max_hamming: int = 8
    # 音频默认精确匹配；预留汉明阈值供未来声纹摘要（chromaprint 落地后启用）


@dataclass(frozen=True)
class DuplicateMatch:
    layer: DuplicateLayer
    similarity: float


@dataclass(frozen=True)
class DuplicateGroup:
    group_id: str
    member_asset_ids: tuple[str, ...]
    layers: tuple[DuplicateLayer, ...]  # 组内连边命中的层（去重排序）
    similarity: float  # 组内最高相似度（代表值）
    matches: tuple[DuplicateMatch, ...] = field(default_factory=tuple)


def _match(a: AssetFingerprint, b: AssetFingerprint, cfg: DedupConfig) -> DuplicateMatch | None:
    """两资产是否为重复，返回命中层 + 相似度；否则 None。优先级：文件>视频>音频>文本。"""
    if a.sha256 and a.sha256 == b.sha256:
        return DuplicateMatch(DuplicateLayer.FILE, 1.0)
    if a.video_phashes and b.video_phashes:
        sim = phash_sequence_similarity(
            a.video_phashes, b.video_phashes, frame_max_hamming=cfg.video_frame_max_hamming
        )
        if sim >= cfg.video_seq_min_similarity:
            return DuplicateMatch(DuplicateLayer.VIDEO, sim)
    if a.audio_fingerprint and b.audio_fingerprint and a.audio_fingerprint == b.audio_fingerprint:
        return DuplicateMatch(DuplicateLayer.AUDIO, 1.0)
    # 0 是空文本的 SimHash（text_simhash("")==0），与 None 一样视为「无文本」不参与匹配——
    # 否则两个空转录会以 similarity=1.0 误聚
    if a.text_simhash and b.text_simhash:
        h = hamming(a.text_simhash, b.text_simhash)
        if h <= cfg.text_max_hamming:
            return DuplicateMatch(DuplicateLayer.TEXT, 1.0 - h / _SIMHASH_BITS)
    return None


class _UnionFind:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)


def _group_id(member_ids: tuple[str, ...]) -> str:
    # 用 \x00 分隔（ULID/合法 id 不含空字节），避免含分隔符的 id 造成理论碰撞
    material = "\x00".join(member_ids).encode("utf-8")
    return "dg-" + hashlib.blake2b(material, digest_size=8).hexdigest()


def find_duplicate_groups(
    fingerprints: list[AssetFingerprint],
    config: DedupConfig | None = None,
) -> list[DuplicateGroup]:
    """指纹集合 → duplicate group 列表（只含 ≥2 成员的组）。确定性、可重放、不删来源。"""
    cfg = config or DedupConfig()
    n = len(fingerprints)
    uf = _UnionFind(n)
    # (i, j) → DuplicateMatch；并查集连通分量即组
    edges: list[tuple[int, int, DuplicateMatch]] = []
    for i in range(n):
        for j in range(i + 1, n):
            m = _match(fingerprints[i], fingerprints[j], cfg)
            if m is not None:
                uf.union(i, j)
                edges.append((i, j, m))

    members_by_root: dict[int, list[int]] = {}
    for idx in range(n):
        members_by_root.setdefault(uf.find(idx), []).append(idx)

    groups: list[DuplicateGroup] = []
    for members in members_by_root.values():
        if len(members) < 2:  # 无重复的资产不成组（不删除、也不虚构单例组）
            continue
        member_set = set(members)
        group_edges = [m for (i, j, m) in edges if i in member_set and j in member_set]
        layers = tuple(sorted({m.layer for m in group_edges}, key=lambda x: x.value))
        member_ids = tuple(sorted(fingerprints[k].asset_id for k in members))
        best = max(group_edges, key=lambda m: m.similarity)
        groups.append(
            DuplicateGroup(
                group_id=_group_id(member_ids),
                member_asset_ids=member_ids,
                layers=layers,
                similarity=best.similarity,
                matches=tuple(sorted(group_edges, key=lambda m: (-m.similarity, m.layer.value))),
            )
        )
    groups.sort(key=lambda g: g.group_id)
    return groups
