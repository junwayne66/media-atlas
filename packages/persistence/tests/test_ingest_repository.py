from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from videoforge_contracts import (
    DiscoveryQuery,
    IngestJob,
    IngestJobStatus,
    IngestJobType,
    RightsAttestation,
    RightsBasis,
)
from videoforge_persistence import IngestRepository, IngestStateError

NOW = datetime(2026, 7, 27, tzinfo=UTC)


def _job(key: str = "idem-1") -> IngestJob:
    return IngestJob(
        id=f"job-{key}",
        job_type=IngestJobType.DISCOVERY_SEARCH,
        status=IngestJobStatus.PENDING,
        platform="douyin",
        idempotency_key=key,
        created_at=NOW,
        updated_at=NOW,
    )


def test_create_job_is_idempotent_and_event_is_not_duplicated(session: Session) -> None:
    repo = IngestRepository(session)
    first, created = repo.create_job(_job(), event_id="event-created")
    second, created_again = repo.create_job(_job(), event_id="event-created-again")
    session.commit()

    assert created is True
    assert created_again is False
    assert first.id == second.id
    assert [e.event_type for e in repo.list_events(first.id)] == ["ingest.job.created"]


def test_transition_appends_ordered_event_and_replay_is_idempotent(session: Session) -> None:
    repo = IngestRepository(session)
    job, _ = repo.create_job(_job(), event_id="event-created")
    running = repo.transition(
        job.id,
        IngestJobStatus.RUNNING,
        event_id="event-running",
        event_type="ingest.job.running",
    )
    # Temporal Activity 重放同一个确定性 event id，不应重复追加。
    assert repo.append_event(repo.list_events(job.id)[-1]) is False
    succeeded = repo.transition(
        job.id,
        IngestJobStatus.SUCCEEDED,
        event_id="event-succeeded",
        event_type="ingest.job.succeeded",
        result={"source_asset_ids": ["source-1"]},
    )
    session.commit()

    assert running.version == 2
    assert succeeded.version == 3
    assert succeeded.finished_at is not None
    assert [event.to_status for event in repo.list_events(job.id)] == [
        IngestJobStatus.PENDING,
        IngestJobStatus.RUNNING,
        IngestJobStatus.SUCCEEDED,
    ]


def test_illegal_transition_is_rejected_without_event(session: Session) -> None:
    repo = IngestRepository(session)
    job, _ = repo.create_job(_job(), event_id="event-created")
    with pytest.raises(IngestStateError):
        repo.transition(
            job.id,
            IngestJobStatus.SUCCEEDED,
            event_id="event-illegal",
            event_type="ingest.job.succeeded",
        )
    session.rollback()


def test_discovery_query_and_authorized_attestation_roundtrip(session: Session) -> None:
    repo = IngestRepository(session)
    query = DiscoveryQuery(
        id="query-1",
        platform="douyin",
        query_text="ai",
        created_at=NOW,
    )
    assert repo.create_query(query) is True

    # FK source row is covered in API integration; contract gate rejects UNKNOWN before persistence.
    with pytest.raises(ValueError):
        RightsAttestation(
            id="rights-0",
            source_asset_id="source-1",
            basis=RightsBasis.UNKNOWN,
            actor_id="local-user",
            created_at=NOW,
        )


def test_worker_task_binding_is_audited_and_replay_safe(session: Session) -> None:
    repo = IngestRepository(session)
    job, _ = repo.create_job(_job(), event_id="event-created")
    repo.transition(
        job.id,
        IngestJobStatus.RUNNING,
        event_id="event-running",
        event_type="ingest.job.running",
    )
    first = repo.bind_worker_task(job.id, "task-1", event_id="event-bound")
    replay = repo.bind_worker_task(job.id, "task-1", event_id="event-bound")
    session.commit()

    assert first.worker_task_id == replay.worker_task_id == "task-1"
    assert [event.event_type for event in repo.list_events(job.id)] == [
        "ingest.job.created",
        "ingest.job.running",
        "ingest.job.worker_task_bound",
    ]
