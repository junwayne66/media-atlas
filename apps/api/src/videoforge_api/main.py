from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from videoforge_api.artifact_uploads import DbArtifactUploadGateway
from videoforge_api.artifact_uploads import router as artifact_uploads_router
from videoforge_api.creation import DbCreationGateway
from videoforge_api.creation import router as creation_router
from videoforge_api.ingest import DbTemporalIngestService
from videoforge_api.ingest import router as ingest_router
from videoforge_api.operations import TemporalOperationsService
from videoforge_api.operations import router as operations_router
from videoforge_api.performance import DbPerformanceGateway
from videoforge_api.performance import router as performance_router
from videoforge_api.projects import DbProjectGateway
from videoforge_api.projects import router as projects_router
from videoforge_api.publish import DbPublishGateway
from videoforge_api.publish import router as publish_router
from videoforge_api.readiness import DbIngestReadinessGateway
from videoforge_api.readiness import router as readiness_router
from videoforge_api.review import DbReviewGateway
from videoforge_api.review import router as review_router
from videoforge_api.secure_settings import DbSettingsGateway, redacted_validation_error_handler
from videoforge_api.secure_settings import router as secure_settings_router
from videoforge_api.settings import Settings
from videoforge_api.sources import DbSourceGateway
from videoforge_api.sources import router as sources_router
from videoforge_api.trends import DbTrendGateway
from videoforge_api.trends import router as trends_router
from videoforge_api.workers import DbWorkerGateway
from videoforge_api.workers import router as workers_router
from videoforge_media_core import ArtifactStore, ObjectStore, S3Settings
from videoforge_persistence import create_engine_from_env


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="VideoForge API", version=settings.version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 懒连接：不触发对应路由就不连 Temporal/DB；测试可整体替换 state 上的实现
    app.state.operations_service = TemporalOperationsService(
        settings.temporal_address, settings.temporal_namespace
    )
    engine = create_engine_from_env(settings.database_url)
    app.state.ingest_service = DbTemporalIngestService(
        engine, settings.temporal_address, settings.temporal_namespace
    )
    object_store = ObjectStore(S3Settings.from_env())
    app.state.artifact_upload_gateway = DbArtifactUploadGateway(engine, ArtifactStore(object_store))
    app.state.ingest_readiness_gateway = DbIngestReadinessGateway(engine, object_store)
    app.state.worker_gateway = DbWorkerGateway(engine)
    app.state.trend_gateway = DbTrendGateway(engine)
    app.state.source_gateway = DbSourceGateway(engine)
    app.state.project_gateway = DbProjectGateway(engine)
    app.state.creation_gateway = DbCreationGateway(engine, staging_dir=settings.render_staging_dir)
    app.state.review_gateway = DbReviewGateway(engine)
    # 发布/指标执行器均为 Fake（零 live network）——真实平台接入属 stop-condition，
    # 集成测试可整体替换这两个 gateway 注入 challenge/限流等分支。
    app.state.publish_gateway = DbPublishGateway(engine)
    app.state.performance_gateway = DbPerformanceGateway(engine)
    # 单进程长期实例：解锁态只存在内存；reload/重启会自然回到 LOCKED。
    app.state.settings_gateway = DbSettingsGateway(engine)
    app.include_router(operations_router)
    app.include_router(ingest_router)
    app.include_router(artifact_uploads_router)
    app.include_router(readiness_router)
    app.include_router(workers_router)
    app.include_router(trends_router)
    app.include_router(sources_router)
    app.include_router(projects_router)
    app.include_router(creation_router)
    app.include_router(review_router)
    app.include_router(publish_router)
    app.include_router(performance_router)
    app.include_router(secure_settings_router)
    app.add_exception_handler(RequestValidationError, redacted_validation_error_handler)

    @app.middleware("http")
    async def no_store_settings(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(("/v1/settings", "/v1/ingest/jobs")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.service_name,
            "version": settings.version,
        }

    @app.get("/v1")
    def v1_root() -> dict[str, str]:
        return {"service": settings.service_name, "api_version": "v1"}

    return app


app = create_app()
