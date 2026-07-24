from collections.abc import Callable
from time import monotonic
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("upload-api")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Structured logging middleware using structlog."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = monotonic()
        path = request.url.path
        method = request.method
        client_host = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (monotonic() - start) * 1000
            logger.exception(
                "request_failed",
                method=method,
                path=path,
                client_ip=client_host,
                duration_ms=duration_ms,
            )
            raise

        duration_ms = (monotonic() - start) * 1000
        logger.info(
            "request",
            method=method,
            path=path,
            status_code=response.status_code,
            client_ip=client_host,
            duration_ms=duration_ms,
        )
        return response


def configure_structlog() -> None:
    """Configure structlog for JSON logging."""
    processors: list[Callable[..., Any]] = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.EventRenamer("event"),
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(20),
        cache_logger_on_first_use=True,
    )
