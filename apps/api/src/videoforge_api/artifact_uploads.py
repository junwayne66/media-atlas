"""Ingest job-scoped staging/commit API.

预签名 URL 只在 stage 响应和 Edge Agent 内存中短暂存在，不能进入任务信封、业务表或事件。
"""

from __future__ import annotations

from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from videoforge_contracts import (
    Artifact,
    IngestJobStatus,
    IngestJobType,
    ProducedBy,
    RightsBasis,
    SourceDisposition,
)
from videoforge_media_core import (
    ArtifactStore,
    StagedUploadMismatch,
    StagedUploadNotFound,
)
from videoforge_persistence import (
    ArtifactRepository,
    IngestRepository,
    NotFoundError,
    SourceAssetRepository,
    record_event,
    session_scope,
)


class ArtifactStageView(BaseModel):
    upload_id: str
    put_url: str
    expires_at: str


class ArtifactCommitRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: Literal["video/mp4"] = "video/mp4"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1, le=512 * 1024 * 1024)


class ArtifactUploadStateError(RuntimeError):
    pass


class ArtifactUploadGateway(Protocol):
    def stage(self, job_id: str) -> ArtifactStageView: ...

    def commit(self, job_id: str, upload_id: str, request: ArtifactCommitRequest) -> Artifact: ...


class DbArtifactUploadGateway:
    def __init__(self, engine: Engine, artifacts: ArtifactStore) -> None:
        self._engine = engine
        self._artifacts = artifacts

    def _eligible_job(self, job_id: str):
        with session_scope(self._engine) as session:
            job = IngestRepository(session).get_job(job_id)
            if job.job_type is not IngestJobType.MEDIA_ACQUIRE:
                raise ArtifactUploadStateError("只有 MEDIA_ACQUIRE 任务可以上传媒体")
            if job.status is not IngestJobStatus.RUNNING:
                raise ArtifactUploadStateError("只有 RUNNING 获取任务可以上传媒体")
            if job.source_asset_id is None:
                raise ArtifactUploadStateError("获取任务缺少 source_asset_id")
            source = SourceAssetRepository(session).get(job.source_asset_id)
            if source.rights_basis is RightsBasis.UNKNOWN:
                raise ArtifactUploadStateError("UNKNOWN 使用依据禁止对象写入")
            return job

    def stage(self, job_id: str) -> ArtifactStageView:
        self._eligible_job(job_id)
        self._artifacts.ensure_bucket()
        staged = self._artifacts.stage_upload(namespace=f"ingest/{job_id}", expires_s=900)
        return ArtifactStageView(
            upload_id=staged.upload_id,
            put_url=staged.put_url,
            expires_at=staged.expires_at.isoformat(),
        )

    def commit(self, job_id: str, upload_id: str, request: ArtifactCommitRequest) -> Artifact:
        job = self._eligible_job(job_id)
        inspection = self._artifacts.inspect_staged_media(
            upload_id,
            namespace=f"ingest/{job_id}",
            mime_type=request.mime_type,
            expected_sha256=request.sha256,
            expected_size=request.size_bytes,
        )
        artifact = self._artifacts.commit(
            upload_id,
            namespace=f"ingest/{job_id}",
            filename=request.filename,
            mime_type=request.mime_type,
            kind="source_video",
            artifact_namespace="ingest",
            expected_sha256=inspection.sha256,
            expected_size=inspection.size_bytes,
            media=inspection.media,
            produced_by=ProducedBy(
                activity="source.acquire",
                tool="fixture.synthetic-mp4",
                tool_version="1",
            ),
        )
        assert job.source_asset_id is not None
        with session_scope(self._engine) as session:
            # 对象已提交后再次锁定并验证状态；并发取消会留下可发现孤儿，绝不错误落库。
            current_job = IngestRepository(session).get_job(job_id, for_update=True)
            if current_job.status is not IngestJobStatus.RUNNING:
                raise ArtifactUploadStateError("任务已离开 RUNNING，提交被拒绝")
            source_repo = SourceAssetRepository(session)
            source = source_repo.get(job.source_asset_id)
            if source.rights_basis is RightsBasis.UNKNOWN:
                raise ArtifactUploadStateError("UNKNOWN 使用依据禁止 Artifact 落库")
            ArtifactRepository(session).add(artifact)
            updated = source.model_copy(
                update={
                    "disposition": SourceDisposition.IMPORTED,
                    "reason": "经授权的合成媒体已完成完整性校验并保存",
                    "artifact_ids": [*source.artifact_ids, artifact.id],
                }
            )
            source_repo.update(updated, expected_version=source.version)
            record_event(
                session,
                aggregate_type="source_asset",
                aggregate_id=source.id,
                event_type="source.media_acquired",
                payload={
                    "source_asset_id": source.id,
                    "artifact_id": artifact.id,
                    "ingest_job_id": job_id,
                    "sha256": artifact.sha256,
                },
            )
        return artifact


router = APIRouter(prefix="/v1/ingest/jobs", tags=["ingest-uploads"])


def get_gateway(request: Request) -> ArtifactUploadGateway:
    return request.app.state.artifact_upload_gateway


GatewayDep = Annotated[ArtifactUploadGateway, Depends(get_gateway)]


@router.post("/{job_id}/artifact-uploads", status_code=201)
def stage_upload(job_id: str, gateway: GatewayDep) -> ArtifactStageView:
    try:
        return gateway.stage(job_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"ingest job 不存在: {job_id}") from None
    except ArtifactUploadStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post("/{job_id}/artifact-uploads/{upload_id}/commit", status_code=201)
def commit_upload(
    job_id: str,
    upload_id: str,
    body: ArtifactCommitRequest,
    gateway: GatewayDep,
) -> Artifact:
    try:
        return gateway.commit(job_id, upload_id, body)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"ingest job 不存在: {job_id}") from None
    except StagedUploadNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except (ArtifactUploadStateError, StagedUploadMismatch) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


__all__ = [
    "ArtifactCommitRequest",
    "ArtifactStageView",
    "DbArtifactUploadGateway",
    "router",
]
