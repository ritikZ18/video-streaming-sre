from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.config import get_settings
from app.middleware.cors import add_cors_middleware
from app.middleware.logging import LoggingMiddleware, configure_structlog
from app.middleware.metrics import MetricsMiddleware
from app.middleware.security import MaxBodySizeMiddleware, RateLimitMiddleware
from app.routes import admin, health, interp, live, movies, tmdb, upload
from app.routes import status as status_routes
from app.services import live_scheduler

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run the live lifecycle reconciler for the life of the process (auto
    go-live on encoder connect, auto-end, scheduled start/stop)."""
    task: asyncio.Task | None = None
    if get_settings().live_scheduler_enabled:
        task = asyncio.create_task(live_scheduler.run())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    settings = get_settings()
    configure_structlog()

    app = FastAPI(
        title="StreamSRE Upload API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )

    # Middleware
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        MaxBodySizeMiddleware,
        max_bytes=settings.max_upload_size_mb * 1024 * 1024,
    )
    add_cors_middleware(app)

    # Routers
    app.include_router(health.router)
    app.include_router(upload.router)
    app.include_router(interp.router)
    app.include_router(status_routes.router)
    app.include_router(movies.router)
    app.include_router(admin.router)
    app.include_router(tmdb.router)
    app.include_router(live.router)

    return app


app = create_app()


