import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

# 本机 Docker Desktop 拒绝 Ryuk 回收器的 socket 挂载容器启动（daemon 500）；
# 清理由 PostgresContainer 的上下文管理器负责。CI 如需 Ryuk 可显式设为 false。
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).parents[3]
ALL_TABLES = (
    "processed_events",
    "outbox_events",
    "artifacts",
    "projects",
    "worker_tasks",
    "workers",
)


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    if not _docker_available():
        pytest.skip("docker 不可用，跳过持久化集成测试（CI 的 macOS runner 属预期跳过）")
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[Engine]:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(migrated_engine: Engine) -> Iterator[None]:
    """每个测试后清空全部表——含绕过 session fixture、直接用 engine 提交的测试。"""
    yield
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(ALL_TABLES)} CASCADE"))


@pytest.fixture()
def session(migrated_engine: Engine) -> Iterator[Session]:
    with Session(migrated_engine) as s:
        yield s
        s.rollback()
