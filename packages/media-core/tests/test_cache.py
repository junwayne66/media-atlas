import hashlib

import httpx
import pytest

from videoforge_media_core import ArtifactStore, LocalArtifactCache, ObjectIntegrityError

DATA = b"cacheable-bytes-" * 500
SHA = hashlib.sha256(DATA).hexdigest()


def _committed_artifact(artifact_store: ArtifactStore):
    staged = artifact_store.stage_upload()
    httpx.put(staged.put_url, content=DATA, timeout=30).raise_for_status()
    return artifact_store.commit(
        staged.upload_id, filename="c.mp4", mime_type="video/mp4", kind="proxy"
    )


def test_ensure_pulls_from_store_then_hits_local(
    tmp_path, artifact_store: ArtifactStore, object_store
) -> None:
    cache = LocalArtifactCache(tmp_path / "cache")
    artifact = _committed_artifact(artifact_store)

    assert not cache.has(artifact.sha256)
    path = cache.ensure(artifact, object_store)
    assert path.read_bytes() == DATA
    assert cache.has(artifact.sha256)
    assert path == cache.path_for(artifact.sha256)
    # 二次命中不回源（对象删掉也能命中即为证明）
    object_store.delete(artifact.storage.object_key)
    assert cache.ensure(artifact, object_store).read_bytes() == DATA


def test_corrupted_cache_entry_refetched(
    tmp_path, artifact_store: ArtifactStore, object_store
) -> None:
    cache = LocalArtifactCache(tmp_path / "cache")
    artifact = _committed_artifact(artifact_store)
    path = cache.ensure(artifact, object_store)
    path.write_bytes(b"corrupted")  # 篡改缓存

    healed = cache.ensure(artifact, object_store)
    assert healed.read_bytes() == DATA


def test_put_file_verifies_hash(tmp_path) -> None:
    cache = LocalArtifactCache(tmp_path / "cache")
    f = tmp_path / "x.bin"
    f.write_bytes(DATA)
    assert cache.put_file(f, SHA).read_bytes() == DATA
    with pytest.raises(ObjectIntegrityError):
        cache.put_file(f, "0" * 64)
