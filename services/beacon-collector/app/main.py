from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.metrics.registry import metrics_endpoint
from app.routes import beacon, health


def create_app() -> FastAPI:
    app = FastAPI(
        title="StreamSRE Beacon Collector",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # The player POSTs beacons cross-origin (fire-and-forget needs no CORS), but
    # the admin dashboard READS GET /stats, which does. Local dev → allow all.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(beacon.router)

    @app.get("/metrics")
    async def metrics_route():
        return await metrics_endpoint(None)  # type: ignore[arg-type]

    return app


app = create_app()

