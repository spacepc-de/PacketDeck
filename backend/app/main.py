from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.event_bus import event_bus
from app.core.logging import configure_logging
from app.meshcore.manager import MeshCoreManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.meshcore_manager = MeshCoreManager(settings, event_bus)
    await app.state.meshcore_manager.start()
    yield
    await app.state.meshcore_manager.shutdown()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
