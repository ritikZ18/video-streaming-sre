from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class Job:
    job_id: str
    movie_id: str
    target_fps: int
    key: str  # idempotency key: "<movie_id>:<target_fps>"
    status: str = "queued"
    stage: str | None = None
    progress: int = 0
    source_fps: float | None = None
    output: dict[str, Any] | None = None
    detail: str | None = None
    gpu: bool = False
    elapsed: float = 0.0


class Registry:
    """In-memory job registry with idempotency on ``key``. A duplicate request
    for an in-flight (movie_id, target_fps) folds into the running job; once a
    job is terminal its key is freed so a later re-request can start fresh."""

    def __init__(self) -> None:
        self._by_id: dict[str, Job] = {}
        self._active_key: dict[str, str] = {}
        self._lock = threading.Lock()

    def find_active(self, key: str) -> Job | None:
        with self._lock:
            jid = self._active_key.get(key)
            return self._by_id.get(jid) if jid else None

    def create(self, job: Job) -> None:
        with self._lock:
            self._by_id[job.job_id] = job
            self._active_key[job.key] = job.job_id

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._by_id.get(job_id)

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._by_id.get(job_id)
            if not job:
                return
            for name, value in fields.items():
                setattr(job, name, value)
            if job.status in ("done", "failed") and self._active_key.get(job.key) == job_id:
                del self._active_key[job.key]


REGISTRY = Registry()
