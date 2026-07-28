import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

REPO_ROOT = Path(__file__).parents[3]
_TRUNCATE = (
    "ingest_job_events",
    "ingest_jobs",
    "rights_attestations",
    "discovery_queries",
    "source_profiles",
    "credential_entries",
    "credential_vault_metadata",
    "provider_configurations",
    "platform_account_bindings",
    "performance_snapshots",
    "publish_jobs",
    "review_decisions",
    "creative_documents",
    "trend_clusters",
    "trend_item_snapshots",
    "source_assets",
    "analysis_runs",
    "analysis_artifacts",
    "projects",
    "outbox_events",
    "processed_events",
    "artifacts",
    "worker_tasks",
    "workers",
)

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="session")
def migrated_engine() -> Iterator[Engine]:
    if not _docker_available():
        pytest.skip("docker 不可用，跳过 API 集成测试")
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        url = pg.get_connection_url()
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        yield engine
        engine.dispose()


@pytest.fixture(autouse=True)
def _clean(request: pytest.FixtureRequest) -> Iterator[None]:
    if request.node.get_closest_marker("no_db") is not None:
        yield
        return
    migrated_engine: Engine = request.getfixturevalue("migrated_engine")
    yield
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TRUNCATE)} CASCADE"))
