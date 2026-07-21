import asyncio
import logging
import os
from pathlib import Path

from videoforge_edge_agent import logsafe
from videoforge_edge_agent.client import ControlPlaneClient
from videoforge_edge_agent.runner import AgentRunner
from videoforge_provider_sdk import FakeProvider, ProviderRegistry, scan_descriptors

logger = logging.getLogger("videoforge.edge_agent")


def build_registry(connectors_dir: Path) -> ProviderRegistry:
    """P0：connectors/ 下的 descriptor 全部实例化为 FakeProvider（先假后真）。"""
    registry = ProviderRegistry()
    for descriptor in scan_descriptors(connectors_dir):
        registry.register(FakeProvider(descriptor))
    return registry


async def run_agent() -> None:
    base_url = os.environ.get("VIDEOFORGE_CONTROL_PLANE_URL", "http://localhost:8000")
    connectors_dir = Path(
        os.environ.get("VIDEOFORGE_CONNECTORS_DIR", Path(__file__).parents[4] / "connectors")
    )
    client = ControlPlaneClient(base_url)
    runner = AgentRunner(
        client,
        build_registry(connectors_dir),
        worker_name=os.environ.get("VIDEOFORGE_WORKER_NAME", "edge-agent"),
    )
    try:
        await runner.run_forever()
    finally:
        await client.aclose()


def cli() -> None:
    logging.basicConfig(level=logging.INFO)
    logsafe.install(logging.getLogger())  # 根 logger 装 Secret 洗涤
    logger.info("edge-agent starting")
    asyncio.run(run_agent())


if __name__ == "__main__":
    cli()
