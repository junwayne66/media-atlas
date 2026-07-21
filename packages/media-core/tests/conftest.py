import os
import subprocess
from collections.abc import Iterator

import pytest

from videoforge_media_core import ArtifactStore, ObjectStore, S3Settings

# 与 persistence 测试同因：本机 Docker Desktop 拒绝 Ryuk 的 socket 挂载容器
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="session")
def object_store() -> Iterator[ObjectStore]:
    if not _docker_available():
        pytest.skip("docker 不可用，跳过对象存储集成测试（CI 的 macOS runner 属预期跳过）")
    from testcontainers.minio import MinioContainer

    with MinioContainer("minio/minio:latest") as minio:
        host_port = minio.get_exposed_port(9000)
        settings = S3Settings(
            endpoint_url=f"http://localhost:{host_port}",
            access_key=minio.access_key,
            secret_key=minio.secret_key,
            bucket="videoforge-test",
        )
        store = ObjectStore(settings)
        store.ensure_bucket()
        yield store


@pytest.fixture()
def artifact_store(object_store: ObjectStore) -> ArtifactStore:
    return ArtifactStore(object_store, tenant_id="t-test")
