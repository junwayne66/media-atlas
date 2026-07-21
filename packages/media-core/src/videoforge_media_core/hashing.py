import hashlib
from pathlib import Path
from typing import BinaryIO

_CHUNK = 1 << 20  # 1 MiB


def sha256_stream(stream: BinaryIO) -> tuple[str, int]:
    """流式计算 sha256 与字节数，不整块读入内存（媒体文件可达数 GiB）。"""
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(_CHUNK):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def sha256_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as f:
        return sha256_stream(f)
