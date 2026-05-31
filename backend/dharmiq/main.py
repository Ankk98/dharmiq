from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from dharmiq.api.routes import health
from dharmiq.config.settings import get_settings
from dharmiq.core.logging import get_logger, setup_logging
from dharmiq.db.session import close_db, init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings)
    logger.info("starting_app", env=settings.env)
    await init_db(settings)
    yield
    await close_db()
    logger.info("stopped_app")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Dharmiq",
        description="Open-source Indian legal information assistant",
        version="0.1.0",
        lifespan=lifespan,
        debug=settings.server.debug,
    )
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "dharmiq.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
