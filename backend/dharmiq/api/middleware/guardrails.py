from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import InputValidationError, RateLimitExceededError
from dharmiq.guardrails.input_validator import validate_message
from dharmiq.guardrails.rate_limiter import check_rate_limit
from dharmiq.redis_client import get_redis

_SESSION_MESSAGE_PATH = re.compile(
    r"^/api/chat/sessions/[0-9a-f-]{36}/messages$",
    re.IGNORECASE,
)


def _is_chat_message_post(path: str, method: str) -> bool:
    if method != "POST":
        return False
    if path == "/api/chat":
        return True
    return _SESSION_MESSAGE_PATH.match(path) is not None


def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip()


def _decode_user_id(token: str, settings: Settings) -> str | None:
    try:
        payload = jwt.decode(
            token,
            settings.auth.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if subject is None:
        return None
    return str(subject)


def _extract_message_content(path: str, body: dict[str, Any]) -> str | None:
    if path == "/api/chat":
        content = body.get("message")
        return content if isinstance(content, str) else None
    content = body.get("content")
    return content if isinstance(content, str) else None


def input_validation_response(exc: InputValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )


def rate_limit_response(exc: RateLimitExceededError) -> JSONResponse:
    headers: dict[str, str] = {}
    if exc.retry_after_seconds is not None:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(
        status_code=429,
        content={
            "code": "RATE_LIMIT_EXCEEDED",
            "message": exc.message,
            "details": exc.details,
        },
        headers=headers,
    )


class ChatGuardrailsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not _is_chat_message_post(path, request.method):
            return await call_next(request)

        body_bytes = await request.body()

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request = Request(request.scope, receive)

        settings = get_settings()
        token = _extract_bearer_token(request)
        if token is None:
            return await call_next(request)

        user_id = _decode_user_id(token, settings)
        if user_id is None:
            return await call_next(request)

        try:
            redis_client = await get_redis(settings)
            rate_result = await check_rate_limit(
                redis_client,
                user_id=user_id,
                settings=settings.guardrails,
            )
            if not rate_result.allowed:
                return rate_limit_response(
                    RateLimitExceededError(
                        rate_result.reason or "Rate limit exceeded",
                        retry_after_seconds=rate_result.retry_after_seconds,
                        details={"window": rate_result.window},
                    )
                )
        except Exception:
            pass

        if not body_bytes:
            return await call_next(request)

        try:
            body = json.loads(body_bytes)
        except json.JSONDecodeError:
            return await call_next(request)

        if not isinstance(body, dict):
            return await call_next(request)

        content = _extract_message_content(path, body)
        if content is None:
            return await call_next(request)

        validation = validate_message(
            content,
            max_length=settings.guardrails.max_message_length,
        )
        if not validation.allowed:
            return input_validation_response(
                InputValidationError(
                    validation.reason or "Invalid input",
                    code=validation.code or "INPUT_INVALID",
                    details={"risk_flags": validation.risk_flags},
                )
            )

        return await call_next(request)
