from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from videoforge_api.operations import TemporalOperationsService
from videoforge_api.operations import router as operations_router
from videoforge_api.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="VideoForge API", version=settings.version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 懒连接：不触发 /v1/operations 就不会尝试连 Temporal；测试可整体替换
    app.state.operations_service = TemporalOperationsService(
        settings.temporal_address, settings.temporal_namespace
    )
    app.include_router(operations_router)

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
