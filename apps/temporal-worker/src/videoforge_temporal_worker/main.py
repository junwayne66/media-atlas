import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from videoforge_persistence import create_engine_from_env
from videoforge_temporal_worker.dispatch import LeaseDispatchActivities
from videoforge_temporal_worker.ingest_activities import IngestActivities
from videoforge_workflows import (
    ALL_ACTIVITIES,
    CORE_TASK_QUEUE,
    IngestWorkflow,
    PipelineSkeletonWorkflow,
    PipelineViaLeaseWorkflow,
)

logger = logging.getLogger("videoforge.worker")


async def run_worker() -> None:
    address = os.environ.get("VIDEOFORGE_TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("VIDEOFORGE_TEMPORAL_NAMESPACE", "default")
    client = await Client.connect(address, namespace=namespace)

    # 派发 Activity 需要 DB 访问（enqueue/轮询 worker-task）；读取 VIDEOFORGE_DATABASE_URL
    engine = create_engine_from_env()
    dispatch = LeaseDispatchActivities(engine)
    ingest = IngestActivities(engine)

    logger.info("worker connected to %s (queue=%s)", address, CORE_TASK_QUEUE)
    # 同步 Activity（dispatch_to_worker）需线程池执行器；异步 Activity 不占用它
    with ThreadPoolExecutor(max_workers=16) as executor:
        worker = Worker(
            client,
            task_queue=CORE_TASK_QUEUE,
            workflows=[PipelineSkeletonWorkflow, PipelineViaLeaseWorkflow, IngestWorkflow],
            activities=[
                *ALL_ACTIVITIES,
                dispatch.dispatch_to_worker,
                ingest.persist_ingest_stage,
            ],
            activity_executor=executor,
        )
        await worker.run()


def cli() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())


if __name__ == "__main__":
    cli()
