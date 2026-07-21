"""内容寻址本地 Artifact 缓存：{cache_dir}/{sha256[:2]}/{sha256}。

读取前校验哈希；损坏条目自动废弃并从对象存储重拉（30 §7 缓存状态语义）。
"""

import shutil
import tempfile
from pathlib import Path

from videoforge_contracts import Artifact
from videoforge_media_core.errors import ObjectIntegrityError
from videoforge_media_core.hashing import sha256_file
from videoforge_media_core.object_store import ObjectStore


class LocalArtifactCache:
    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, sha256: str) -> Path:
        return self._dir / sha256[:2] / sha256

    def has(self, sha256: str) -> bool:
        return self.path_for(sha256).is_file()

    def put_file(self, source: Path, sha256: str) -> Path:
        actual, _ = sha256_file(source)
        if actual != sha256:
            raise ObjectIntegrityError(f"写入缓存的内容哈希不符: 期望 {sha256}，实际 {actual}")
        target = self.path_for(sha256)
        target.parent.mkdir(parents=True, exist_ok=True)
        # 随机 tmp 名：并发写同哈希互不共享临时路径；replace 原子落位
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            shutil.copyfile(source, tmp_path)
            tmp_path.replace(target)
        finally:
            tmp_path.unlink(missing_ok=True)
        return target

    def ensure(self, artifact: Artifact, objects: ObjectStore) -> Path:
        """返回本地路径；缺失或损坏时从对象存储拉取并校验。"""
        target = self.path_for(artifact.sha256)
        if target.is_file():
            actual, _ = sha256_file(target)
            if actual == artifact.sha256:
                return target
            target.unlink()  # 损坏条目：废弃重拉

        if artifact.storage.object_key is None:
            raise ObjectIntegrityError(f"artifact {artifact.id} 没有对象存储键，无法回源")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with (
                tmp_path.open("wb") as out,
                objects.open_stream(artifact.storage.object_key) as body,
            ):
                shutil.copyfileobj(body, out)
            actual, _ = sha256_file(tmp_path)
            if actual != artifact.sha256:
                raise ObjectIntegrityError(
                    f"回源内容与 Artifact 记录不符: 期望 {artifact.sha256}，实际 {actual}"
                )
            tmp_path.replace(target)
        finally:
            tmp_path.unlink(missing_ok=True)  # 下载/校验中途异常不残留临时文件
        return target
