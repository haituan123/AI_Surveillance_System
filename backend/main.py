from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import CORS_ORIGINS, ensure_runtime_directories
from backend.app.database import init_db
from backend.routes import (
    alert_routes,
    camera_routes,
    log_routes,
    member_routes,
    qa_routes,
    surveillance_routes,
    system_routes,
    video_analysis_routes,
    zone_routes,
)
from backend.services.surveillance_manager import surveillance_manager
from backend.services.video_analysis_manager import video_analysis_manager
from backend.services.qa_video_index_manager import qa_video_index_manager


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_runtime_directories()
    init_db()
    yield
    surveillance_manager.shutdown()
    video_analysis_manager.shutdown()
    qa_video_index_manager.shutdown()


def create_app(*, initialize_database: bool = True) -> FastAPI:
    app_lifespan = lifespan if initialize_database else None
    application = FastAPI(
        title="AI Face Security Backend",
        lifespan=app_lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials="*" not in CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(system_routes.router)
    application.include_router(member_routes.router)
    application.include_router(camera_routes.router)
    application.include_router(surveillance_routes.router)
    application.include_router(log_routes.router)
    application.include_router(alert_routes.router)
    application.include_router(video_analysis_routes.router)
    application.include_router(zone_routes.router)
    application.include_router(qa_routes.router)
    return application


app = create_app()
