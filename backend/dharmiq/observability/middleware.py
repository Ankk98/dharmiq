from __future__ import annotations

import re
import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from dharmiq.observability.metrics import record_http_request

_UUID_PATTERN = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def normalize_path(path: str) -> str:
    """Collapse UUID path segments for low-cardinality Prometheus labels."""
    return _UUID_PATTERN.sub("/{id}", path)


class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        started = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - started
        record_http_request(
            method=request.method,
            path=normalize_path(request.url.path),
            status_code=response.status_code,
            duration_seconds=duration,
        )
        return response
