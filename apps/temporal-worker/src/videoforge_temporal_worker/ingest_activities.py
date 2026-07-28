"""IngestWorkflow 的控制面持久化 Activities（VF-108）。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine
from temporalio import activity

from videoforge_contracts import (
    IngestJobStatus,
    SourceAsset,
    SourceAssetKind,
    SourceDisposition,
    SourcePublicMetadata,
    StageOutcome,
)
from videoforge_contracts.ids import new_id
from videoforge_persistence import (
    DuplicateError,
    IngestRepository,
    SourceAssetRepository,
    record_event,
    session_scope,
)
from videoforge_workflows import PERSIST_INGEST_ACTIVITY, IngestPersistRequest


def _snapshot_metadata(snapshot: dict) -> SourcePublicMetadata:
    return SourcePublicMetadata(
        author_platform_id=snapshot.get("author_id"),
        published_at=snapshot.get("published_at"),
        stats={
            key: snapshot.get(key)
            for key in ("views", "likes", "comments", "shares", "saves", "rank")
            if snapshot.get(key) is not None
        },
        raw_metadata={
            "snapshot_id": snapshot.get("id"),
            "collector_version": snapshot.get("collector_version"),
            "hashtag_ids": snapshot.get("hashtag_ids") or [],
            "sound_id": snapshot.get("sound_id"),
            "source_confidence": snapshot.get("source_confidence"),
        },
    )


class IngestActivities:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @activity.defn(name=PERSIST_INGEST_ACTIVITY)
    def persist_ingest_stage(self, request: IngestPersistRequest) -> None:
        outcome = None if request.outcome is None else StageOutcome.model_validate(request.outcome)
        with session_scope(self._engine) as session:
            repo = IngestRepository(session)
            result = None if outcome is None else dict(outcome.result)
            if request.status is IngestJobStatus.SUCCEEDED and outcome is not None:
                source_ids = self._persist_sources(session, request.job_id, outcome)
                result = {**result, "source_asset_ids": source_ids}
            repo.transition(
                request.job_id,
                request.status,
                event_id=request.event_id,
                event_type=request.event_type,
                worker_task_id=request.worker_task_id,
                attempt=request.attempt,
                result=result,
                error_code=None if outcome is None else outcome.error_code,
                error_message=None if outcome is None else outcome.message,
                details=(
                    {}
                    if outcome is None
                    else {
                        "stage_status": str(outcome.status),
                        "debug_artifact_ids": outcome.debug_artifact_ids,
                    }
                ),
            )

    @staticmethod
    def _persist_sources(session, job_id: str, outcome: StageOutcome) -> list[str]:
        source_repo = SourceAssetRepository(session)
        sources: list[dict] = []
        if "source" in outcome.result:
            sources.append(outcome.result["source"])
        for snapshot in outcome.result.get("snapshots", []):
            item_id = str(snapshot["item_id"])
            sources.append(
                {
                    "platform": "douyin",
                    "content_id": item_id,
                    "canonical_url": f"https://www.douyin.com/video/{item_id}",
                    "original_input": f"https://www.douyin.com/video/{item_id}",
                    "observed_at": snapshot["observed_at"],
                    "public_metadata": _snapshot_metadata(snapshot).model_dump(mode="json"),
                }
            )

        ids: list[str] = []
        for data in sources:
            platform = str(data.get("platform") or "douyin")
            content_id = data.get("content_id")
            existing = source_repo.find_existing(platform=platform, content_id=content_id)
            if existing is not None:
                public_metadata = (
                    existing.public_metadata
                    if data.get("public_metadata") is None
                    else SourcePublicMetadata.model_validate(data["public_metadata"])
                )
                observed_at = data.get("observed_at")
                if isinstance(observed_at, str):
                    observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
                source_repo.update(
                    existing.model_copy(
                        update={
                            "public_metadata": public_metadata,
                            "last_seen_at": observed_at or datetime.now(UTC),
                        }
                    ),
                    expected_version=existing.version,
                )
                ids.append(existing.id)
                continue
            now = datetime.now(UTC)
            observed_at = data.get("observed_at")
            if isinstance(observed_at, str):
                observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            observed_at = observed_at or now
            asset = SourceAsset(
                id=new_id(),
                kind=SourceAssetKind.URL,
                original_input=str(data.get("original_input") or data["canonical_url"]),
                platform=platform,
                content_id=content_id,
                canonical_url=data.get("canonical_url"),
                disposition=SourceDisposition.METADATA_ONLY,
                reason="公开元数据已采集，尚未授权获取原始媒体",
                public_metadata=(
                    None
                    if data.get("public_metadata") is None
                    else SourcePublicMetadata.model_validate(data["public_metadata"])
                ),
                discovered_at=observed_at,
                last_seen_at=observed_at,
                created_at=now,
                updated_at=now,
            )
            try:
                # 并发发现同一来源时唯一索引冲突只回滚 SAVEPOINT，父事务仍可重查复用。
                with session.begin_nested():
                    source_repo.create(asset)
            except DuplicateError:
                existing = source_repo.find_existing(platform=platform, content_id=content_id)
                if existing is None:
                    raise
                asset = existing
            else:
                record_event(
                    session,
                    aggregate_type="source_asset",
                    aggregate_id=asset.id,
                    event_type="source.discovered",
                    payload={"source_asset_id": asset.id, "ingest_job_id": job_id},
                )
            ids.append(asset.id)
        return ids


__all__ = ["IngestActivities"]
