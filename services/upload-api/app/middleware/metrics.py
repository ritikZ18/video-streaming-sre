from collections.abc import Callable
from time import monotonic

from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

REQUEST_COUNT = Counter(
    "upload_api_http_requests_total",
    "HTTP requests total",
    ["method", "path", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "upload_api_http_request_duration_seconds",
    "HTTP request duration seconds",
    ["method", "path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

IN_PROGRESS = Gauge(
    "upload_api_http_requests_in_progress",
    "In-progress HTTP requests",
    ["method", "path"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Prometheus metrics for request count, latency, and in-progress gauge."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        path = request.url.path
        if path == "/metrics":
            # Expose Prometheus metrics
            payload = generate_latest()
            return PlainTextResponse(
                content=payload.decode("utf-8"),
                media_type="text/plain; version=0.0.4",
            )

        start = monotonic()
        IN_PROGRESS.labels(method=method, path=path).inc()
        try:
            response = await call_next(request)
        finally:
            duration = monotonic() - start
            IN_PROGRESS.labels(method=method, path=path).dec()

        REQUEST_COUNT.labels(
            method=method,
            path=path,
            status_code=str(response.status_code),
        ).inc()
        REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
        return response


def metrics_app() -> Callable[[Request], Response]:
    """Compatibility stub if we need a dedicated metrics route later."""
    async def endpoint(request: Request) -> Response:  # pragma: no cover - not used directly
        payload = generate_latest()
        return PlainTextResponse(
            content=payload.decode("utf-8"),
            media_type="text/plain; version=0.0.4",
        )

    return endpoint


