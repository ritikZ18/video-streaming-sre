from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings
from app.middleware.cors import add_cors_middleware
from app.middleware.logging import LoggingMiddleware, configure_structlog
from app.middleware.metrics import MetricsMiddleware
from app.middleware.security import MaxBodySizeMiddleware, RateLimitMiddleware
from app.routes import admin, health, interp, movies, upload
from app.routes import status as status_routes


def create_app() -> FastAPI:
    settings = get_settings()
    configure_structlog()

    app = FastAPI(
        title="StreamSRE Upload API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
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

    return app


app = create_app()


