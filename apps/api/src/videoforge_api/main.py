from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from videoforge_api.operations import TemporalOperationsService
from videoforge_api.operations import router as operations_router
from videoforge_api.projects import DbProjectGateway
from videoforge_api.projects import router as projects_router
from videoforge_api.settings import Settings
from videoforge_api.sources import DbSourceGateway
from videoforge_api.sources import router as sources_router
from videoforge_api.trends import DbTrendGateway
from videoforge_api.trends import router as trends_router
from videoforge_api.workers import DbWorkerGateway
from videoforge_api.workers import router as workers_router
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
    app.state.worker_gateway = DbWorkerGateway(engine)
    app.state.trend_gateway = DbTrendGateway(engine)
    app.state.source_gateway = DbSourceGateway(engine)
    app.state.project_gateway = DbProjectGateway(engine)
    app.include_router(operations_router)
    app.include_router(workers_router)
    app.include_router(trends_router)
    app.include_router(sources_router)
    app.include_router(projects_router)

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
