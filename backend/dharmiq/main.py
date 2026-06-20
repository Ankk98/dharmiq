from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from dharmiq import __version__
from dharmiq.api.middleware.guardrails import (
    ChatGuardrailsMiddleware,
    input_validation_response,
    rate_limit_response,
)
from dharmiq.api.routes import auth, chat, chat_attachments, chat_stream, docs, health, metrics, uploads
from dharmiq.config.settings import get_settings
from dharmiq.core.errors import InputValidationError, RateLimitExceededError
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
        version=__version__,
        lifespan=lifespan,
        debug=settings.server.debug,
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api/auth/jwt", tags=["auth"])
    app.include_router(auth.register_router, prefix="/api/auth", tags=["auth"])
    app.include_router(auth.users_router, prefix="/api/users", tags=["users"])
    app.include_router(chat.router, prefix="/api")
    app.include_router(chat_stream.router, prefix="/api")
    app.include_router(chat_attachments.router, prefix="/api")
    app.include_router(uploads.router, prefix="/api")
    app.include_router(docs.router, prefix="/api")
    app.include_router(metrics.router)

    @app.exception_handler(InputValidationError)
    def _handle_input_validation(_request: Request, exc: InputValidationError) -> JSONResponse:
        return input_validation_response(exc)

    @app.exception_handler(RateLimitExceededError)
    def _handle_rate_limit(_request: Request, exc: RateLimitExceededError) -> JSONResponse:
        return rate_limit_response(exc)

    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(ChatGuardrailsMiddleware)
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
