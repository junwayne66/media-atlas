"""Project 列表/详情 + 分析链 API（docs/modules/41 §7–§10 的 REST 面）。

路由薄封装 gateway；gateway 组合 ProjectRepository 与 AnalysisService。
素材没有本地文件时分析返回 **409**（诚实：先人工下载关联，不假装分析）。
"""

from __future__ import annotations

from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from videoforge_api.analysis_service import (
    AnalysisService,
    SourceNotAnalyzable,
    UnsupportedAnalysisLanguage,
)
from videoforge_contracts import Project
from videoforge_persistence import NotFoundError, ProjectRepository, session_scope


class RunAnalysisRequest(BaseModel):
    source_asset_id: str = Field(min_length=1)
    language: str = Field(min_length=2, description="BCP-47，如 zh-CN / en-US")


class AnalysisStageView(BaseModel):
    stage: str
    status: str
    cache_key: str | None = None
    cache_hit: bool = False
    artifact_id: str | None = None
    provider: str | None = None
    error: str | None = None
    issues: list[str] = Field(default_factory=list)


class AnalysisRunView(BaseModel):
    id: str
    project_id: str
    source_asset_id: str
    language: str
    status: str
    stages: list[AnalysisStageView] = Field(default_factory=list)


class ProjectGateway(Protocol):
    def list_projects(self, limit: int) -> list[Project]: ...
    def get_project(self, project_id: str) -> Project: ...
    def run_analysis(self, project_id: str, request: RunAnalysisRequest) -> AnalysisRunView: ...
    def latest_analysis(self, project_id: str) -> AnalysisRunView: ...
    def analysis_artifact(self, project_id: str, kind: str) -> dict[str, Any]: ...


class DbProjectGateway:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._analysis = AnalysisService(engine)

    def list_projects(self, limit: int) -> list[Project]:
        with session_scope(self._engine) as s:
            return ProjectRepository(s).list(limit=limit)

    def get_project(self, project_id: str) -> Project:
        with session_scope(self._engine) as s:
            return ProjectRepository(s).get(project_id)

    def run_analysis(self, project_id: str, request: RunAnalysisRequest) -> AnalysisRunView:
        run = self._analysis.run(project_id, request.source_asset_id, request.language)
        return _run_view(run)

    def latest_analysis(self, project_id: str) -> AnalysisRunView:
        return _run_view(self._analysis.latest_run(project_id))

    def analysis_artifact(self, project_id: str, kind: str) -> dict[str, Any]:
        return self._analysis.latest_artifact(project_id, kind)


def _run_view(run: Any) -> AnalysisRunView:
    return AnalysisRunView(
        id=run.id,
        project_id=run.project_id,
        source_asset_id=run.source_asset_id,
        language=run.language,
        status=run.status,
        stages=[AnalysisStageView.model_validate(st) for st in run.stages],
    )


router = APIRouter(prefix="/v1/projects", tags=["projects"])

# 路径片段 → 产物 kind
_ARTIFACT_PATHS = {
    "transcript": "transcript",
    "text-tracks": "text_track_set",
    "visual": "visual_analysis",
    "blueprint": "video_blueprint",
}


def get_project_gateway(request: Request) -> ProjectGateway:
    return request.app.state.project_gateway


GatewayDep = Annotated[ProjectGateway, Depends(get_project_gateway)]


def _not_found(project_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"project 不存在: {project_id}")


@router.get("")
def list_projects(
    gateway: GatewayDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Project]:
    return gateway.list_projects(limit)


@router.get("/{project_id}")
def get_project(project_id: str, gateway: GatewayDep) -> Project:
    try:
        return gateway.get_project(project_id)
    except NotFoundError:
        raise _not_found(project_id) from None


@router.post("/{project_id}/analysis:run")
def run_analysis(project_id: str, body: RunAnalysisRequest, gateway: GatewayDep) -> AnalysisRunView:
    try:
        return gateway.run_analysis(project_id, body)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except SourceNotAnalyzable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except UnsupportedAnalysisLanguage as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/{project_id}/analysis")
def latest_analysis(project_id: str, gateway: GatewayDep) -> AnalysisRunView:
    try:
        return gateway.latest_analysis(project_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"project {project_id} 尚未做过分析") from None


@router.get("/{project_id}/analysis/{artifact_path}")
def analysis_artifact(project_id: str, artifact_path: str, gateway: GatewayDep) -> dict[str, Any]:
    kind = _ARTIFACT_PATHS.get(artifact_path)
    if kind is None:
        raise HTTPException(status_code=404, detail=f"未知分析产物: {artifact_path}")
    try:
        return gateway.analysis_artifact(project_id, kind)
    except NotFoundError:
        raise HTTPException(
            status_code=404, detail=f"project {project_id} 无 {artifact_path} 产物"
        ) from None
