from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import monotonic

from app.config import get_settings
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


@dataclass
class Bucket:
  tokens: float
  last_refill: float


class RateLimitMiddleware(BaseHTTPMiddleware):
  """Simple in-memory token bucket rate limiter per client IP."""

  def __init__(self, app) -> None:  # type: ignore[override]
    super().__init__(app)
    settings = get_settings()
    self.capacity = float(settings.rate_limit_per_minute)
    self.refill_rate = self.capacity / 60.0  # tokens per second
    self.buckets: defaultdict[str, Bucket] = defaultdict(
      lambda: Bucket(tokens=self.capacity, last_refill=monotonic()),
    )

  async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
    client = request.client.host if request.client else "unknown"
    path = request.url.path

    # Only protect mutating endpoints
    if request.method in {"POST", "PUT", "DELETE"}:
      key = f"{client}:{path}"
      bucket = self.buckets[key]
      now = monotonic()
      elapsed = now - bucket.last_refill
      bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_rate)
      bucket.last_refill = now

      if bucket.tokens < 1.0:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

      bucket.tokens -= 1.0

    return await call_next(request)


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
  """Enforce a maximum request body size in bytes."""

  def __init__(self, app, max_bytes: int) -> None:  # type: ignore[override]
    super().__init__(app)
    self.max_bytes = max_bytes

  async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
    if request.method == "POST":
      content_length = request.headers.get("content-length")
      if content_length is not None:
        try:
          size = int(content_length)
        except ValueError:
          size = 0
        if size > self.max_bytes:
          return JSONResponse(
            status_code=413, content={"detail": "Request body too large"}
          )

    return await call_next(request)


