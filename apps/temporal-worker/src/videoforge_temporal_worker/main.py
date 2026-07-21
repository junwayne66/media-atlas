import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.worker import Worker

from videoforge_workflows import ALL_ACTIVITIES, CORE_TASK_QUEUE, PipelineSkeletonWorkflow

logger = logging.getLogger("videoforge.worker")


async def run_worker() -> None:
    address = os.environ.get("VIDEOFORGE_TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("VIDEOFORGE_TEMPORAL_NAMESPACE", "default")
    client = await Client.connect(address, namespace=namespace)
    logger.info("worker connected to %s (queue=%s)", address, CORE_TASK_QUEUE)
    worker = Worker(
        client,
        task_queue=CORE_TASK_QUEUE,
        workflows=[PipelineSkeletonWorkflow],
        activities=ALL_ACTIVITIES,
    )
    await worker.run()


def cli() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())


if __name__ == "__main__":
    cli()
