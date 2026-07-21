import hashlib

import httpx
import pytest

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
