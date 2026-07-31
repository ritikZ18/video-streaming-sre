"""I/O Framer — frames in, interpolated frames out.

A standalone RIFE (intermediate-flow) FPS-boost sidecar over Vulkan. Implements
the contract in ../CONTRACT.md. Phase 2: runnable in isolation; not yet wired to
the transcode worker.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import FastAPI, HTTPException, status

from app import engine
from app.config import get_settings
from app.jobs import REGISTRY, Job
from app.pipeline import run_pipeline
from app.schemas import (
    Health,
    InterpolateAccepted,
    InterpolateRequest,
    JobStatus,
    Metrics,
    OutputInfo,
)

app = FastAPI(title="I/O Framer", version="0.2.0")

# One interpolation at a time — the GPU (or lavapipe) is the bottleneck and must
# not be oversubscribed. Held for the whole decode→RIFE→encode pass.
_SEM = asyncio.Semaphore(1)
_TASKS: set[asyncio.Task] = set()


@app.get("/healthz", response_model=Health)
def healthz() -> Health:
    s = get_settings()
    backend, gpu, devices = engine.detect_backend()
    return Health(
        status="ok" if backend != "none" else "degraded",
        backend=backend,
        gpu=gpu,
        model=s.rife_model,
        devices=devices,
    )


async def _run(
    job_id: str, target_fps: int,
    sb: str, sk: str, ob: str, ok: str, gpu: bool,
) -> None:
    async with _SEM:
        await asyncio.to_thread(
            run_pipeline, job_id, "", target_fps, sb, sk, ob, ok, gpu
        )


@app.post(
    "/interpolate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=InterpolateAccepted,
)
async def interpolate(req: InterpolateRequest) -> InterpolateAccepted:
    s = get_settings()
    if req.target_fps < 1 or req.target_fps > s.interp_max_target_fps:
        raise HTTPException(
            status_code=400,
            detail=f"target_fps must be between 1 and {s.interp_max_target_fps}",
        )

    key = f"{req.movie_id}:{req.target_fps}"
    existing = REGISTRY.find_active(key)
    if existing:  # idempotent: fold a duplicate into the in-flight job
        state = existing.status if existing.status in ("queued", "processing") else "queued"
        return InterpolateAccepted(job_id=existing.job_id, status=state)  # type: ignore[arg-type]

    _, gpu, _ = engine.detect_backend()
    job_id = f"if_{uuid.uuid4().hex[:12]}"
    REGISTRY.create(
        Job(job_id=job_id, movie_id=req.movie_id, target_fps=req.target_fps, key=key, gpu=gpu)
    )
    task = asyncio.create_task(
        _run(
            job_id, req.target_fps,
            req.source.s3_bucket, req.source.s3_key,
            req.output.s3_bucket, req.output.s3_key, gpu,
        )
    )
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return InterpolateAccepted(job_id=job_id, status="queued")


@app.get("/interpolate/{job_id}", response_model=JobStatus)
def job_status(job_id: str) -> JobStatus:
    job = REGISTRY.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="unknown job")
    out = OutputInfo(**job.output) if job.output else None
    metrics = (
        Metrics(gpu=job.gpu, elapsed_seconds=round(job.elapsed, 1)) if job.elapsed else None
    )
    return JobStatus(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        stage=job.stage,
        progress=job.progress,
        source_fps=job.source_fps,
        target_fps=job.target_fps,
        output=out,
        detail=job.detail,
        metrics=metrics,
    )
