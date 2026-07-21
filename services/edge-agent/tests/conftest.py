import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config

from videoforge_api.main import create_app
from videoforge_api.settings import Settings
from videoforge_edge_agent.client import ControlPlaneClient

REPO_ROOT = Path(__file__).parents[3]

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    if not _docker_available():
        pytest.skip("docker 不可用，跳过 edge-agent 集成测试")
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        url = pg.get_connection_url()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        yield url


@pytest.fixture()
def api_app(database_url: str):
    return create_app(Settings(database_url=database_url))


@pytest.fixture()
async def control_plane(api_app) -> AsyncIterator[ControlPlaneClient]:
    # ASGITransport 直连 FastAPI 应用：全链路走真实路由与真实 Postgres，不开端口
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://control-plane") as http:
        yield ControlPlaneClient("http://control-plane", client=http)
