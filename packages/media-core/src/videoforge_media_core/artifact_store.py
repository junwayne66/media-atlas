"""staging → 原子提交的 Artifact 上传流程（docs/architecture/30 §5/§7）。

产物先上传到 staging 临时键；commit 时服务端流式验哈希，通过后 copy 到
规范键并返回填好的 Artifact 合同对象。持久化（ArtifactRepository）由
application 层组合完成——media-core 不依赖 persistence。

崩溃窗口语义：copy 成功但调用方未落库时会留下孤儿对象，可按 artifact_id
不在库中垃圾回收；staging 前缀按时间批量清理。两者都不产生错误的 Artifact 记录。
"""

import hashlib
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from videoforge_contracts import Artifact, MediaProbe, ProducedBy, StorageRef
from videoforge_contracts.ids import new_id
from videoforge_media_core.errors import StagedUploadMismatch, StagedUploadNotFound
from videoforge_media_core.hashing import sha256_stream
from videoforge_media_core.object_store import ObjectStore
from videoforge_media_core.probe import FfprobeProbeProvider, ProbeProvider

_STAGING_PREFIX = "staging"
_DEFAULT_MAX_MEDIA_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class StagedUpload:
    upload_id: str
    key: str
    put_url: str
    expires_at: datetime


@dataclass(frozen=True)
class StagedMediaInspection:
    sha256: str
    size_bytes: int
    mime_type: str
    media: MediaProbe


def _safe_filename(filename: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name
    if not name or name in {".", ".."}:
        raise ValueError(f"非法文件名: {filename!r}")
    return name


def _safe_namespace(namespace: str | None) -> str:
    if namespace is None:
        return ""
    parts = PurePosixPath(namespace.replace("\\", "/")).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"非法 staging namespace: {namespace!r}")
    if any(not part.replace("-", "").replace("_", "").isalnum() for part in parts):
        raise ValueError(f"非法 staging namespace: {namespace!r}")
    return "/".join(parts)


class ArtifactStore:
    def __init__(self, objects: ObjectStore, *, tenant_id: str = "default") -> None:
        self._objects = objects
        self._tenant_id = tenant_id

    def ensure_bucket(self) -> None:
        self._objects.ensure_bucket()

    def stage_upload(self, *, expires_s: int = 3600, namespace: str | None = None) -> StagedUpload:
        upload_id = new_id()
        safe_namespace = _safe_namespace(namespace)
        key = "/".join(part for part in (_STAGING_PREFIX, safe_namespace, upload_id) if part)
        return StagedUpload(
            upload_id=upload_id,
            key=key,
            put_url=self._objects.presign_put(key, expires_s=expires_s),
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_s),
        )

    def _find_staging_key(self, upload_id: str, namespace: str | None) -> str:
        safe_namespace = _safe_namespace(namespace)
        return "/".join(part for part in (_STAGING_PREFIX, safe_namespace, upload_id) if part)

    def inspect_staged_media(
        self,
        upload_id: str,
        *,
        namespace: str | None,
        mime_type: str,
        expected_sha256: str,
        expected_size: int,
        max_size_bytes: int = _DEFAULT_MAX_MEDIA_BYTES,
        probe: ProbeProvider | None = None,
    ) -> StagedMediaInspection:
        """流式复核媒体声明并用 ffprobe 验证可读性；失败不生成 Artifact。"""
        if mime_type != "video/mp4":
            raise StagedUploadMismatch(f"不支持的媒体类型: {mime_type}")
        if expected_size < 1 or expected_size > max_size_bytes:
            raise StagedUploadMismatch(
                f"媒体大小超出允许范围: {expected_size}（上限 {max_size_bytes}）"
            )
        staging_key = self._find_staging_key(upload_id, namespace)
        head = self._objects.head(staging_key)
        if head is None:
            raise StagedUploadNotFound(f"staging 对象不存在: {upload_id}")
        content_length = int(head.get("ContentLength", -1))
        if content_length != expected_size:
            self._objects.delete(staging_key)
            raise StagedUploadMismatch(
                f"Content-Length 不符: 声明 {expected_size}，实际 {content_length}"
            )

        digest = hashlib.sha256()
        total = 0
        header = b""
        with tempfile.NamedTemporaryFile(suffix=".mp4") as temp:
            with self._objects.open_stream(staging_key) as body:
                while chunk := body.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_size_bytes:
                        self._objects.delete(staging_key)
                        raise StagedUploadMismatch("媒体超过大小上限")
                    if len(header) < 16:
                        header += chunk[: 16 - len(header)]
                    digest.update(chunk)
                    temp.write(chunk)
            temp.flush()
            actual_sha = digest.hexdigest()
            if total != expected_size or actual_sha != expected_sha256:
                self._objects.delete(staging_key)
                raise StagedUploadMismatch("媒体 size/sha256 声明与服务端复核不一致")
            if len(header) < 12 or header[4:8] != b"ftyp":
                self._objects.delete(staging_key)
                raise StagedUploadMismatch("媒体容器签名不是 MP4/ISO BMFF")
            try:
                media = (probe or FfprobeProbeProvider()).probe(Path(temp.name))
            except Exception as exc:
                self._objects.delete(staging_key)
                raise StagedUploadMismatch("ffprobe 无法读取媒体") from exc
        if media.duration_s is None or media.width is None or media.height is None:
            self._objects.delete(staging_key)
            raise StagedUploadMismatch("媒体缺少时长或画面尺寸")
        return StagedMediaInspection(
            sha256=actual_sha,
            size_bytes=total,
            mime_type=mime_type,
            media=media,
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
        namespace: str | None = None,
        artifact_namespace: str | None = None,
        media: MediaProbe | None = None,
    ) -> Artifact:
        """验证 staging 对象并原子迁移到规范键，返回 Artifact 合同（未落库）。

        中断/篡改防线：服务端重新流式计算 sha256/size，与声明值不符即拒绝
        并清理 staging——绝不产出哈希与内容不符的 Artifact。

        并发注记：head→copy 非事务，同一 upload_id 的并发 commit 可能各自
        通过检查产出两条 Artifact；任务级幂等由上层按 task_id+output_digest
        保证（30 §5），单 worker 语义下无此竞争。
        """
        staging_key = self._find_staging_key(upload_id, namespace)
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
        final_scope = (
            _safe_namespace(artifact_namespace)
            if artifact_namespace is not None
            else project_id or "_unassigned"
        )
        final_key = f"artifacts/{self._tenant_id}/{final_scope}/{aid}/{safe_name}"
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
            media=media,
            storage=StorageRef(backend="s3", bucket=self._objects.bucket, object_key=final_key),
            created_at=datetime.now(UTC),
        )

    def presigned_get(self, artifact: Artifact, *, expires_s: int = 600) -> str:
        if artifact.storage.object_key is None:
            raise ValueError(f"artifact {artifact.id} 没有对象存储键")
        return self._objects.presign_get(artifact.storage.object_key, expires_s=expires_s)

    def cleanup_staging(
        self,
        *,
        namespace: str,
        older_than: datetime,
    ) -> list[str]:
        """只清理显式采集 namespace 下超过安全窗口的 staging 对象。"""
        safe_namespace = _safe_namespace(namespace)
        prefix = f"{_STAGING_PREFIX}/{safe_namespace}/"
        deleted: list[str] = []
        for item in self._objects.list_objects(prefix):
            key = str(item["Key"])
            last_modified = item.get("LastModified")
            if isinstance(last_modified, datetime) and last_modified < older_than:
                self._objects.delete(key)
                deleted.append(key)
        return deleted

    def cleanup_orphan_artifacts(
        self,
        *,
        namespace: str,
        known_artifact_ids: set[str],
        older_than: datetime,
    ) -> list[str]:
        """清理指定 namespace 中已过安全窗口且数据库不存在的最终对象。"""
        safe_namespace = _safe_namespace(namespace)
        prefix = f"artifacts/{self._tenant_id}/{safe_namespace}/"
        deleted: list[str] = []
        for item in self._objects.list_objects(prefix):
            key = str(item["Key"])
            parts = PurePosixPath(key).parts
            if len(parts) < 5:
                continue
            artifact_id = parts[3]
            last_modified = item.get("LastModified")
            if (
                artifact_id not in known_artifact_ids
                and isinstance(last_modified, datetime)
                and last_modified < older_than
            ):
                self._objects.delete(key)
                deleted.append(key)
        return deleted
