from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dharmiq.api.routes import auth, chat, docs, health, metrics, uploads
from dharmiq.config.settings import get_settings
from dharmiq.core.logging import get_logger, setup_logging
from dharmiq.db.session import close_db, init_db
from dharmiq.llm.openrouter_client import close_openrouter_client
from dharmiq.observability.middleware import PrometheusMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings)
    logger.info("starting_app", env=settings.env)
    await init_db(settings)
    yield
    await close_openrouter_client()
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
    app.include_router(auth.router, prefix="/api/auth/jwt", tags=["auth"])
    app.include_router(auth.register_router, prefix="/api/auth", tags=["auth"])
    app.include_router(auth.users_router, prefix="/api/users", tags=["users"])
    app.include_router(chat.router, prefix="/api")
    app.include_router(uploads.router, prefix="/api")
    app.include_router(docs.router, prefix="/api")
    app.include_router(metrics.router)
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
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
