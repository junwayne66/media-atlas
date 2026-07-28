import hashlib
import io
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from videoforge_contracts import MediaProbe
from videoforge_media_core import (
    ArtifactStore,
    StagedUploadMismatch,
    StagedUploadNotFound,
)

DATA = b"fake-mp4-bytes-" * 1000
SHA = hashlib.sha256(DATA).hexdigest()


def _upload(staged, data: bytes) -> None:
    resp = httpx.put(staged.put_url, content=data, timeout=30)
    resp.raise_for_status()


def test_stage_commit_and_presigned_get_roundtrip(artifact_store: ArtifactStore) -> None:
    staged = artifact_store.stage_upload()
    _upload(staged, DATA)
    artifact = artifact_store.commit(
        staged.upload_id,
        filename="clip.mp4",
        mime_type="video/mp4",
        kind="source_video",
        project_id="p1",
        expected_sha256=SHA,
        expected_size=len(DATA),
    )
    assert artifact.sha256 == SHA
    assert artifact.size_bytes == len(DATA)
    assert artifact.storage.object_key == f"artifacts/t-test/p1/{artifact.id}/clip.mp4"

    url = artifact_store.presigned_get(artifact)
    fetched = httpx.get(url, timeout=30)
    fetched.raise_for_status()
    assert fetched.content == DATA


def test_interrupted_upload_rejected(artifact_store: ArtifactStore) -> None:
    """DoD：中断上传。截断内容与声明 size/sha 不符，提交必须失败且不产出 Artifact。"""
    staged = artifact_store.stage_upload()
    _upload(staged, DATA[: len(DATA) // 2])  # 模拟传一半断开
    with pytest.raises(StagedUploadMismatch, match="size 不符"):
        artifact_store.commit(
            staged.upload_id,
            filename="clip.mp4",
            mime_type="video/mp4",
            kind="source_video",
            expected_sha256=SHA,
            expected_size=len(DATA),
        )
    # staging 已被清理，重试需重新 stage
    with pytest.raises(StagedUploadNotFound):
        artifact_store.commit(
            staged.upload_id, filename="clip.mp4", mime_type="video/mp4", kind="source_video"
        )


def test_tampered_content_rejected(artifact_store: ArtifactStore) -> None:
    staged = artifact_store.stage_upload()
    _upload(staged, DATA + b"tampered")
    with pytest.raises(StagedUploadMismatch, match="sha256 不符"):
        artifact_store.commit(
            staged.upload_id,
            filename="clip.mp4",
            mime_type="video/mp4",
            kind="source_video",
            expected_sha256=SHA,
        )


def test_commit_without_upload_raises(artifact_store: ArtifactStore) -> None:
    staged = artifact_store.stage_upload()
    with pytest.raises(StagedUploadNotFound):
        artifact_store.commit(
            staged.upload_id, filename="a.mp4", mime_type="video/mp4", kind="source_video"
        )


def test_commit_consumes_staging_exactly_once(artifact_store: ArtifactStore) -> None:
    """DoD：重复 Artifact。同一 staging 只能提交一次；任务级幂等由 idempotency_key 层负责。"""
    staged = artifact_store.stage_upload()
    _upload(staged, DATA)
    artifact_store.commit(
        staged.upload_id, filename="a.mp4", mime_type="video/mp4", kind="source_video"
    )
    with pytest.raises(StagedUploadNotFound):
        artifact_store.commit(
            staged.upload_id, filename="a.mp4", mime_type="video/mp4", kind="source_video"
        )


def test_same_content_two_sources_two_artifacts(artifact_store: ArtifactStore) -> None:
    """DoD：不同来源同哈希。内容相同的两次独立提交产生两条记录、两个对象，均可取回。"""
    artifacts = []
    for name in ("from_douyin.mp4", "from_tiktok.mp4"):
        staged = artifact_store.stage_upload()
        _upload(staged, DATA)
        artifacts.append(
            artifact_store.commit(
                staged.upload_id, filename=name, mime_type="video/mp4", kind="source_video"
            )
        )
    a1, a2 = artifacts
    assert a1.sha256 == a2.sha256 == SHA
    assert a1.id != a2.id
    assert a1.storage.object_key != a2.storage.object_key
    for a in artifacts:
        resp = httpx.get(artifact_store.presigned_get(a), timeout=30)
        assert resp.content == DATA


def test_path_traversal_filename_neutralized(artifact_store: ArtifactStore) -> None:
    staged = artifact_store.stage_upload()
    _upload(staged, DATA)
    artifact = artifact_store.commit(
        staged.upload_id,
        filename="../../etc/passwd",
        mime_type="video/mp4",
        kind="source_video",
    )
    assert artifact.filename == "passwd"
    assert ".." not in artifact.storage.object_key


class _MemoryObjects:
    bucket = "memory"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.modified: dict[str, datetime] = {}

    def presign_put(self, key: str, *, expires_s: int) -> str:
        return f"https://uploads.invalid/{key}?expires={expires_s}"

    def head(self, key: str) -> dict | None:
        data = self.objects.get(key)
        return None if data is None else {"ContentLength": len(data)}

    def open_stream(self, key: str) -> io.BytesIO:
        return io.BytesIO(self.objects[key])

    def copy(self, src_key: str, dst_key: str) -> None:
        self.objects[dst_key] = self.objects[src_key]
        self.modified[dst_key] = datetime.now(UTC)

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def list_objects(self, prefix: str) -> list[dict]:
        return [
            {"Key": key, "LastModified": self.modified[key]}
            for key in self.objects
            if key.startswith(prefix)
        ]

    def presign_get(self, key: str, *, expires_s: int) -> str:
        return f"https://downloads.invalid/{key}?expires={expires_s}"


class _SyntheticProbe:
    def probe(self, _path) -> MediaProbe:
        return MediaProbe(duration_s=1.0, fps=1.0, width=16, height=16, codec="h264")


def test_ingest_namespace_inspection_and_commit() -> None:
    objects = _MemoryObjects()
    store = ArtifactStore(objects)  # type: ignore[arg-type]
    staged = store.stage_upload(namespace="ingest/job-1")
    payload = b"\x00\x00\x00\x18ftypisom" + b"fixture-media"
    objects.objects[staged.key] = payload
    objects.modified[staged.key] = datetime.now(UTC)
    digest = hashlib.sha256(payload).hexdigest()

    inspection = store.inspect_staged_media(
        staged.upload_id,
        namespace="ingest/job-1",
        mime_type="video/mp4",
        expected_sha256=digest,
        expected_size=len(payload),
        probe=_SyntheticProbe(),
    )
    artifact = store.commit(
        staged.upload_id,
        namespace="ingest/job-1",
        filename="source.mp4",
        mime_type="video/mp4",
        kind="source_video",
        expected_sha256=digest,
        expected_size=len(payload),
        media=inspection.media,
    )
    assert artifact.media is not None
    assert artifact.media.duration_s == 1.0
    assert staged.key not in objects.objects


def test_ingest_media_rejects_size_type_signature_and_namespace_escape() -> None:
    objects = _MemoryObjects()
    store = ArtifactStore(objects)  # type: ignore[arg-type]
    staged = store.stage_upload(namespace="ingest/job-1")
    objects.objects[staged.key] = b"not-an-mp4"
    objects.modified[staged.key] = datetime.now(UTC)
    digest = hashlib.sha256(objects.objects[staged.key]).hexdigest()
    with pytest.raises(StagedUploadMismatch, match="容器签名"):
        store.inspect_staged_media(
            staged.upload_id,
            namespace="ingest/job-1",
            mime_type="video/mp4",
            expected_sha256=digest,
            expected_size=len(objects.objects[staged.key]),
            probe=_SyntheticProbe(),
        )
    with pytest.raises(ValueError, match="namespace"):
        store.stage_upload(namespace="../other-job")


def test_cleanup_only_deletes_old_objects_inside_selected_namespace() -> None:
    objects = _MemoryObjects()
    store = ArtifactStore(objects)  # type: ignore[arg-type]
    now = datetime.now(UTC)
    objects.objects = {
        "staging/ingest/job-1/old": b"x",
        "staging/ingest/job-1/new": b"x",
        "staging/other/old": b"x",
    }
    objects.modified = {
        "staging/ingest/job-1/old": now - timedelta(days=2),
        "staging/ingest/job-1/new": now,
        "staging/other/old": now - timedelta(days=2),
    }
    deleted = store.cleanup_staging(
        namespace="ingest/job-1", older_than=now - timedelta(days=1)
    )
    assert deleted == ["staging/ingest/job-1/old"]
    assert "staging/ingest/job-1/new" in objects.objects
    assert "staging/other/old" in objects.objects


def test_cleanup_ingest_orphans_keeps_known_and_other_namespaces() -> None:
    objects = _MemoryObjects()
    store = ArtifactStore(objects, tenant_id="tenant")  # type: ignore[arg-type]
    now = datetime.now(UTC)
    objects.objects = {
        "artifacts/tenant/ingest/orphan/source.mp4": b"x",
        "artifacts/tenant/ingest/known/source.mp4": b"x",
        "artifacts/tenant/project-1/orphan/source.mp4": b"x",
    }
    objects.modified = {
        key: now - timedelta(days=2) for key in objects.objects
    }
    deleted = store.cleanup_orphan_artifacts(
        namespace="ingest",
        known_artifact_ids={"known"},
        older_than=now - timedelta(days=1),
    )
    assert deleted == ["artifacts/tenant/ingest/orphan/source.mp4"]
    assert "artifacts/tenant/ingest/known/source.mp4" in objects.objects
    assert "artifacts/tenant/project-1/orphan/source.mp4" in objects.objects
