import hashlib
import io

from videoforge_media_core import sha256_file, sha256_stream


def test_stream_hash_matches_hashlib() -> None:
    data = b"videoforge" * 100_000  # 跨多个 1MiB 分块
    digest, size = sha256_stream(io.BytesIO(data))
    assert digest == hashlib.sha256(data).hexdigest()
    assert size == len(data)


def test_file_hash(tmp_path) -> None:
    p = tmp_path / "a.bin"
    p.write_bytes(b"\x00\x01\x02")
    digest, size = sha256_file(p)
    assert digest == hashlib.sha256(b"\x00\x01\x02").hexdigest()
    assert size == 3
