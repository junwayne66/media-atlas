from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import Engine

from videoforge_api.artifact_uploads import (
    ArtifactCommitRequest,
    ArtifactUploadStateError,
    DbArtifactUploadGateway,
)
from videoforge_api.ingest import (
    AcquisitionStartRequest,
    DbTemporalIngestService,
    IngestControlError,
)
from videoforge_contracts import (
    IngestJob,
    IngestJobStatus,
    RightsBasis,
    SourceAsset,
    SourceAssetKind,
    SourceDisposition,
    StageOutcome,
    StageOutcomeStatus,
)
from videoforge_edge_agent.ingest_provider import DouyinIngestProvider
from videoforge_media_core import ArtifactStore, ObjectStore, S3Settings
from videoforge_persistence import (
    ArtifactRepository,
    IngestRepository,
    SourceAssetRepository,
    session_scope,
)
from videoforge_temporal_worker.ingest_activities import IngestActivities
from videoforge_workflows import IngestPersistRequest


class _TemporalRecorder:
    def __init__(self) -> None:
        self.started: list[dict] = []

    async def start_workflow(self, _run, _input, **kwargs) -> None:
        self.started.append(kwargs)


class _GatewayUploadClient:
    def __init__(self, gateway: DbArtifactUploadGateway) -> None:
        self.gateway = gateway

    async def stage_ingest_artifact(self, job_id: str) -> dict:
        return self.gateway.stage(job_id).model_dump()

    async def put_presigned(self, put_url: str, data: bytes, *, mime_type: str) -> None:
        response = httpx.put(
            put_url,
            content=data,
            headers={"Content-Type": mime_type},
            timeout=30,
        )
        response.raise_for_status()

    async def commit_ingest_artifact(
        self,
        job_id: str,
        upload_id: str,
        *,
        filename: str,
        mime_type: str,
        sha256: str,
        size_bytes: int,
    ) -> dict:
        return self.gateway.commit(
            job_id,
            upload_id,
            ArtifactCommitRequest(
                filename=filename,
                mime_type=mime_type,
                sha256=sha256,
                size_bytes=size_bytes,
            ),
        ).model_dump(mode="json")


class _CancelAfterObjectCommitStore(ArtifactStore):
    def __init__(self, objects: ObjectStore, engine: Engine) -> None:
        super().__init__(objects, tenant_id="orphan-test")
        self._engine = engine

    def commit(self, *args, **kwargs):
        artifact = super().commit(*args, **kwargs)
        namespace = str(kwargs["namespace"])
        job_id = namespace.rsplit("/", 1)[-1]
        with session_scope(self._engine) as session:
            IngestRepository(session).transition(
                job_id,
                IngestJobStatus.CANCELLED,
                event_id=f"cancel-after-object:{job_id}",
                event_type="ingest.job.cancelled",
            )
        return artifact


@pytest.fixture(scope="module")
def ingest_object_store() -> ObjectStore:
    from testcontainers.minio import MinioContainer

    with MinioContainer("minio/minio:latest") as minio:
        store = ObjectStore(
            S3Settings(
                endpoint_url=f"http://localhost:{minio.get_exposed_port(9000)}",
                access_key=minio.access_key,
                secret_key=minio.secret_key,
                bucket="ingest-integration",
            )
        )
        store.ensure_bucket()
        yield store


def _source() -> SourceAsset:
    now = datetime.now(UTC)
    return SourceAsset(
        id="source-acquire",
        kind=SourceAssetKind.URL,
        original_input="https://www.douyin.com/video/7412345678901234567",
        platform="douyin",
        content_id="7412345678901234567",
        canonical_url="https://www.douyin.com/video/7412345678901234567",
        disposition=SourceDisposition.METADATA_ONLY,
        reason="公开元数据已保存",
        created_at=now,
        updated_at=now,
    )


async def test_rights_gate_synthetic_artifact_and_reuse(
    migrated_engine: Engine,
    ingest_object_store: ObjectStore,
) -> None:
    with session_scope(migrated_engine) as session:
        SourceAssetRepository(session).create(_source())

    temporal = _TemporalRecorder()
    service = DbTemporalIngestService(migrated_engine, "unused:7233")
    service._client = temporal  # type: ignore[assignment]
    before = ingest_object_store.list_objects("staging/ingest/")
    with pytest.raises(IngestControlError, match="UNKNOWN"):
        await service.start_acquisition(
            "source-acquire",
            "acquire-denied",
            AcquisitionStartRequest(rights_basis=RightsBasis.UNKNOWN),
        )
    assert ingest_object_store.list_objects("staging/ingest/") == before

    job = await service.start_acquisition(
        "source-acquire",
        "acquire-allowed",
        AcquisitionStartRequest(
            rights_basis=RightsBasis.USER_PROVIDED,
            rights_note="本地合成 Fixture",
        ),
    )
    assert len(temporal.started) == 1
    with session_scope(migrated_engine) as session:
        IngestRepository(session).transition(
            job.id,
            IngestJobStatus.RUNNING,
            event_id="integration-running",
            event_type="ingest.job.running",
        )

    gateway = DbArtifactUploadGateway(
        migrated_engine,
        ArtifactStore(ingest_object_store, tenant_id="ingest-test"),
    )
    staged = gateway.stage(job.id)
    from videoforge_edge_agent.ingest_provider import _SYNTHETIC_MP4

    upload = httpx.put(staged.put_url, content=_SYNTHETIC_MP4, timeout=30)
    upload.raise_for_status()
    import hashlib

    artifact = gateway.commit(
        job.id,
        staged.upload_id,
        ArtifactCommitRequest(
            filename="synthetic-source.mp4",
            sha256=hashlib.sha256(_SYNTHETIC_MP4).hexdigest(),
            size_bytes=len(_SYNTHETIC_MP4),
        ),
    )
    assert artifact.media is not None
    assert artifact.media.duration_s == pytest.approx(1.0, abs=0.01)
    assert (artifact.media.width, artifact.media.height) == (16, 16)

    outcome = StageOutcome(
        status=StageOutcomeStatus.SUCCEEDED,
        result={"artifact_id": artifact.id, "sha256": artifact.sha256},
    )
    IngestActivities(migrated_engine).persist_ingest_stage(
        IngestPersistRequest(
            job_id=job.id,
            status=IngestJobStatus.SUCCEEDED,
            event_id="integration-succeeded",
            event_type="ingest.job.succeeded",
            outcome=outcome.model_dump(mode="json"),
        )
    )
    with session_scope(migrated_engine) as session:
        source = SourceAssetRepository(session).get("source-acquire")
        stored = ArtifactRepository(session).get(artifact.id)
        events = IngestRepository(session).list_events(job.id)
    assert source.artifact_ids == [artifact.id]
    assert source.disposition is SourceDisposition.IMPORTED
    assert stored.sha256 == artifact.sha256
    assert events[-1].to_status is IngestJobStatus.SUCCEEDED

    reused = await service.start_acquisition(
        "source-acquire",
        "acquire-reuse",
        AcquisitionStartRequest(rights_basis=RightsBasis.USER_PROVIDED),
    )
    assert reused.status is IngestJobStatus.SUCCEEDED
    assert reused.result is not None
    assert reused.result["artifact_ids"] == [artifact.id]
    assert len(temporal.started) == 1

    forced = await service.start_acquisition(
        "source-acquire",
        "acquire-force",
        AcquisitionStartRequest(
            rights_basis=RightsBasis.USER_PROVIDED,
            force=True,
        ),
    )
    assert forced.status is IngestJobStatus.PENDING
    assert len(temporal.started) == 2
    with session_scope(migrated_engine) as session:
        IngestRepository(session).transition(
            forced.id,
            IngestJobStatus.RUNNING,
            event_id="force-running",
            event_type="ingest.job.running",
        )
    forced_outcome = StageOutcome.model_validate(
        await DouyinIngestProvider(upload_client=_GatewayUploadClient(gateway)).invoke(
            "source.acquire",
            {
                **forced.payload,
                "job_id": forced.id,
                "platform": "douyin",
            },
        )
    )
    assert forced_outcome.status is StageOutcomeStatus.SUCCEEDED
    assert forced_outcome.result["sha256"] != artifact.sha256
    IngestActivities(migrated_engine).persist_ingest_stage(
        IngestPersistRequest(
            job_id=forced.id,
            status=IngestJobStatus.SUCCEEDED,
            event_id="force-succeeded",
            event_type="ingest.job.succeeded",
            outcome=forced_outcome.model_dump(mode="json"),
        )
    )
    with session_scope(migrated_engine) as session:
        source = SourceAssetRepository(session).get("source-acquire")
        hashes = {
            ArtifactRepository(session).get(artifact_id).sha256
            for artifact_id in source.artifact_ids
        }
    assert source.artifact_ids[0] == artifact.id
    assert len(source.artifact_ids) == 2
    assert len(hashes) == 2


def test_concurrent_discovery_reuses_one_source_fact(migrated_engine: Engine) -> None:
    now = datetime.now(UTC)
    with session_scope(migrated_engine) as session:
        repo = IngestRepository(session)
        for index in (1, 2):
            job_id = f"job-concurrent-{index}"
            repo.create_job(
                IngestJob(
                    id=job_id,
                    job_type="DISCOVERY_SEARCH",
                    status=IngestJobStatus.PENDING,
                    platform="douyin",
                    idempotency_key=f"concurrent-{index}",
                    created_at=now,
                    updated_at=now,
                ),
                event_id=f"created-{index}",
            )
            repo.transition(
                job_id,
                IngestJobStatus.RUNNING,
                event_id=f"running-{index}",
                event_type="ingest.job.running",
            )

    outcome = StageOutcome(
        status=StageOutcomeStatus.SUCCEEDED,
        result={
            "snapshots": [
                {
                    "id": "snapshot-concurrent",
                    "item_id": "same-content",
                    "observed_at": "2026-07-27T00:00:00Z",
                    "collector_version": "fixture@1",
                    "source_confidence": 0.6,
                }
            ]
        },
    ).model_dump(mode="json")

    def persist(index: int) -> None:
        IngestActivities(migrated_engine).persist_ingest_stage(
            IngestPersistRequest(
                job_id=f"job-concurrent-{index}",
                status=IngestJobStatus.SUCCEEDED,
                event_id=f"succeeded-{index}",
                event_type="ingest.job.succeeded",
                outcome=outcome,
            )
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(persist, (1, 2)))

    with session_scope(migrated_engine) as session:
        sources = SourceAssetRepository(session).list(platform="douyin")
        first = IngestRepository(session).get_job("job-concurrent-1")
        second = IngestRepository(session).get_job("job-concurrent-2")
    assert len(sources) == 1
    assert first.result is not None and second.result is not None
    assert first.result["source_asset_ids"] == second.result["source_asset_ids"]


async def test_transaction_race_leaves_discoverable_and_cleanable_orphan(
    migrated_engine: Engine,
    ingest_object_store: ObjectStore,
) -> None:
    source = _source().model_copy(
        update={
            "id": "source-orphan",
            "content_id": "orphan-content",
            "original_input": "https://www.douyin.com/video/orphan-content",
            "canonical_url": "https://www.douyin.com/video/orphan-content",
        }
    )
    with session_scope(migrated_engine) as session:
        SourceAssetRepository(session).create(source)
    temporal = _TemporalRecorder()
    service = DbTemporalIngestService(migrated_engine, "unused:7233")
    service._client = temporal  # type: ignore[assignment]
    job = await service.start_acquisition(
        source.id,
        "acquire-orphan",
        AcquisitionStartRequest(rights_basis=RightsBasis.OWNED),
    )
    with session_scope(migrated_engine) as session:
        IngestRepository(session).transition(
            job.id,
            IngestJobStatus.RUNNING,
            event_id="orphan-running",
            event_type="ingest.job.running",
        )

    store = _CancelAfterObjectCommitStore(ingest_object_store, migrated_engine)
    gateway = DbArtifactUploadGateway(migrated_engine, store)
    staged = gateway.stage(job.id)
    from videoforge_edge_agent.ingest_provider import _SYNTHETIC_MP4

    httpx.put(staged.put_url, content=_SYNTHETIC_MP4, timeout=30).raise_for_status()
    import hashlib

    with pytest.raises(ArtifactUploadStateError, match="离开 RUNNING"):
        gateway.commit(
            job.id,
            staged.upload_id,
            ArtifactCommitRequest(
                filename="orphan.mp4",
                sha256=hashlib.sha256(_SYNTHETIC_MP4).hexdigest(),
                size_bytes=len(_SYNTHETIC_MP4),
            ),
        )
    prefix = "artifacts/orphan-test/ingest/"
    orphaned = ingest_object_store.list_objects(prefix)
    assert len(orphaned) == 1
    with session_scope(migrated_engine) as session:
        assert (
            ArtifactRepository(session).find_by_sha256(hashlib.sha256(_SYNTHETIC_MP4).hexdigest())
            == []
        )
        assert SourceAssetRepository(session).get(source.id).artifact_ids == []
    deleted = store.cleanup_orphan_artifacts(
        namespace="ingest",
        known_artifact_ids=set(),
        older_than=datetime.now(UTC) + timedelta(seconds=1),
    )
    assert deleted == [orphaned[0]["Key"]]
