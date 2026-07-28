from datetime import UTC, datetime

from sqlalchemy import Engine

from videoforge_contracts import (
    IngestJob,
    IngestJobStatus,
    IngestJobType,
    SourceDisposition,
    StageOutcome,
    StageOutcomeStatus,
)
from videoforge_persistence import IngestRepository, SourceAssetRepository, session_scope
from videoforge_temporal_worker.ingest_activities import IngestActivities
from videoforge_workflows import IngestPersistRequest


def _create_running_job(engine: Engine) -> None:
    now = datetime.now(UTC)
    with session_scope(engine) as session:
        repo = IngestRepository(session)
        repo.create_job(
            IngestJob(
                id="job-activity",
                job_type=IngestJobType.DISCOVERY_SEARCH,
                status=IngestJobStatus.PENDING,
                platform="douyin",
                idempotency_key="activity-idem",
                workflow_id="ingest-job-activity",
                created_at=now,
                updated_at=now,
            ),
            event_id="event-created",
        )
        repo.transition(
            "job-activity",
            IngestJobStatus.RUNNING,
            event_id="event-running",
            event_type="ingest.job.running",
        )


def test_success_persists_source_and_replay_is_idempotent(migrated_engine: Engine) -> None:
    _create_running_job(migrated_engine)
    outcome = StageOutcome(
        status=StageOutcomeStatus.SUCCEEDED,
        result={
            "snapshots": [
                {
                    "id": "snapshot-1",
                    "item_id": "dy-7412",
                    "author_id": "author-1",
                    "published_at": "2026-07-21T14:00:00Z",
                    "observed_at": "2026-07-22T00:00:00Z",
                    "views": 123,
                    "likes": 10,
                    "collector_version": "fixture@1",
                    "source_confidence": 0.6,
                }
            ]
        },
    )
    request = IngestPersistRequest(
        job_id="job-activity",
        status=IngestJobStatus.SUCCEEDED,
        event_id="event-succeeded",
        event_type="ingest.job.succeeded",
        worker_task_id="task-1",
        attempt=1,
        outcome=outcome.model_dump(mode="json"),
    )
    activities = IngestActivities(migrated_engine)
    activities.persist_ingest_stage(request)
    activities.persist_ingest_stage(request)

    with session_scope(migrated_engine) as session:
        job = IngestRepository(session).get_job("job-activity")
        sources = SourceAssetRepository(session).list(platform="douyin")
        events = IngestRepository(session).list_events("job-activity")
    assert job.status is IngestJobStatus.SUCCEEDED
    assert job.result is not None
    assert len(job.result["source_asset_ids"]) == 1
    assert len(sources) == 1
    assert sources[0].disposition is SourceDisposition.METADATA_ONLY
    assert sources[0].public_metadata is not None
    assert sources[0].public_metadata.stats["views"] == 123
    assert [event.event_type for event in events] == [
        "ingest.job.created",
        "ingest.job.running",
        "ingest.job.succeeded",
    ]
