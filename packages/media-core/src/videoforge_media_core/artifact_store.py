"""staging → 原子提交的 Artifact 上传流程（docs/architecture/30 §5/§7）。

产物先上传到 staging 临时键；commit 时服务端流式验哈希，通过后 copy 到
规范键并返回填好的 Artifact 合同对象。持久化（ArtifactRepository）由
application 层组合完成——media-core 不依赖 persistence。

崩溃窗口语义：copy 成功但调用方未落库时会留下孤儿对象，可按 artifact_id
不在库中垃圾回收；staging 前缀按时间批量清理。两者都不产生错误的 Artifact 记录。
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from videoforge_contracts import Artifact, ProducedBy, StorageRef
from videoforge_contracts.ids import new_id
from videoforge_media_core.errors import StagedUploadMismatch, StagedUploadNotFound
from videoforge_media_core.hashing import sha256_stream
from videoforge_media_core.object_store import ObjectStore

_STAGING_PREFIX = "staging"


@dataclass(frozen=True)
class StagedUpload:
    upload_id: str
    key: str
    put_url: str
    expires_at: datetime


def _safe_filename(filename: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name
    if not name or name in {".", ".."}:
        raise ValueError(f"非法文件名: {filename!r}")
    return name


class ArtifactStore:
    def __init__(self, objects: ObjectStore, *, tenant_id: str = "default") -> None:
        self._objects = objects
        self._tenant_id = tenant_id

    def stage_upload(self, *, expires_s: int = 3600) -> StagedUpload:
        upload_id = new_id()
        key = f"{_STAGING_PREFIX}/{upload_id}"
        return StagedUpload(
            upload_id=upload_id,
            key=key,
            put_url=self._objects.presign_put(key, expires_s=expires_s),
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_s),
        )

    def commit(
        self,
        upload_id: str,
        *,
        filename: str,
        mime_type: str,
        kind: str,
        project_id: str | None = None,
        artifact_id: str | None = None,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
        produced_by: ProducedBy | None = None,
        upstream_artifact_ids: tuple[str, ...] = (),
    ) -> Artifact:
        """验证 staging 对象并原子迁移到规范键，返回 Artifact 合同（未落库）。

        中断/篡改防线：服务端重新流式计算 sha256/size，与声明值不符即拒绝
        并清理 staging——绝不产出哈希与内容不符的 Artifact。

        并发注记：head→copy 非事务，同一 upload_id 的并发 commit 可能各自
        通过检查产出两条 Artifact；任务级幂等由上层按 task_id+output_digest
        保证（30 §5），单 worker 语义下无此竞争。
        """
        staging_key = f"{_STAGING_PREFIX}/{upload_id}"
        if self._objects.head(staging_key) is None:
            raise StagedUploadNotFound(f"staging 对象不存在: {upload_id}")

        with self._objects.open_stream(staging_key) as body:
            sha256, size = sha256_stream(body)
        if expected_size is not None and size != expected_size:
            self._objects.delete(staging_key)
            raise StagedUploadMismatch(
                f"size 不符: 声明 {expected_size}，实际 {size}（上传可能被中断）"
            )
        if expected_sha256 is not None and sha256 != expected_sha256:
            self._objects.delete(staging_key)
            raise StagedUploadMismatch(f"sha256 不符: 声明 {expected_sha256}，实际 {sha256}")

        safe_name = _safe_filename(filename)
        aid = artifact_id or new_id()
        final_key = f"artifacts/{self._tenant_id}/{project_id or '_unassigned'}/{aid}/{safe_name}"
        self._objects.copy(staging_key, final_key)
        self._objects.delete(staging_key)

        return Artifact(
            id=aid,
            project_id=project_id,
            kind=kind,
            filename=safe_name,
            mime_type=mime_type,
            size_bytes=size,
            sha256=sha256,
            upstream_artifact_ids=list(upstream_artifact_ids),
            produced_by=produced_by,
            storage=StorageRef(backend="s3", bucket=self._objects.bucket, object_key=final_key),
            created_at=datetime.now(UTC),
        )

    def presigned_get(self, artifact: Artifact, *, expires_s: int = 600) -> str:
        if artifact.storage.object_key is None:
            raise ValueError(f"artifact {artifact.id} 没有对象存储键")
        return self._objects.presign_get(artifact.storage.object_key, expires_s=expires_s)
