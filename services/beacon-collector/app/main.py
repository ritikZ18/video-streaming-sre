from __future__ import annotations

from fastapi import FastAPI

from app.metrics.registry import metrics_endpoint
from app.routes import beacon, health


def create_app() -> FastAPI:
    app = FastAPI(
        title="StreamSRE Beacon Collector",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.include_router(health.router)
    app.include_router(beacon.router)

    @app.get("/metrics")
    async def metrics_route():
        return await metrics_endpoint(None)  # type: ignore[arg-type]

    return app


app = create_app()

