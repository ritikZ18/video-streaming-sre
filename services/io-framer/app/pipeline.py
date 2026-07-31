from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from app import engine, ffmpeg, s3
from app.config import Settings, get_settings
from app.jobs import REGISTRY
from app.metrics import IOF_JOB_DURATION, IOF_JOBS_TOTAL


def _u(job_id: str, **f: object) -> None:
    REGISTRY.update(job_id, **f)


def _ensure_workdir(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def _guard(info: dict, target_fps: int, s: Settings) -> None:
    """Re-check the guardrails after probing (defence in depth; the worker will
    have screened these before ever calling us)."""
    if info["height"] > s.interp_max_height:
        raise RuntimeError(f"guardrail: height {info['height']} > {s.interp_max_height}")
    if info["duration"] > s.interp_max_duration_seconds:
        raise RuntimeError(
            f"guardrail: duration {info['duration']:.0f}s > {s.interp_max_duration_seconds}s"
        )
    if info["fps"] and info["fps"] >= s.interp_max_source_fps:
        raise RuntimeError(
            f"guardrail: source {info['fps']:.1f}fps already >= {s.interp_max_source_fps}"
        )
    if target_fps > s.interp_max_target_fps:
        raise RuntimeError(f"guardrail: target {target_fps} > {s.interp_max_target_fps}")


def _disk_preflight(work: Path, width: int, height: int, n_in: int, n_out: int) -> None:
    """Fail fast if the scratch volume can't hold the PNG frames. Estimates ~2
    bytes/pixel per frame (typical photographic PNG after compression) for input +
    output frames, plus 10% for the source/mezzanine. Skips when the frame counts
    are unknown (duration missing)."""
    total_frames = n_in + n_out
    if total_frames <= 0 or width <= 0 or height <= 0:
        return
    needed = int(total_frames * width * height * 2 * 1.1)
    free = shutil.disk_usage(str(work)).free
    if needed > free:
        raise RuntimeError(
            f"insufficient scratch: ~{needed // (1 << 30)}GiB needed for "
            f"{total_frames} frames, ~{free // (1 << 30)}GiB free"
        )


def run_pipeline(
    job_id: str,
    movie_id: str,
    target_fps: int,
    src_bucket: str,
    src_key: str,
    out_bucket: str,
    out_key: str,
    gpu: bool,
) -> None:
    """Blocking decode → RIFE → encode → upload. Runs in a worker thread behind
    the GPU semaphore; all state flows back through the registry."""
    s = get_settings()
    started = time.monotonic()
    work = Path(tempfile.mkdtemp(prefix=f"iof-{job_id}-", dir=_ensure_workdir(s.work_dir)))
    try:
        _u(job_id, status="processing", stage="downloading", progress=5)
        input_path = work / f"input{Path(src_key).suffix or '.mp4'}"
        s3.download(src_bucket, src_key, str(input_path))

        _u(job_id, stage="probing", progress=10)
        info = ffmpeg.probe(str(input_path))
        src_fps = info["fps"] or 0.0
        duration = info["duration"] or 0.0
        _u(job_id, source_fps=src_fps)
        _guard(info, target_fps, s)

        # Bail before extracting anything if the scratch volume is too small.
        est_in = round(duration * src_fps) if duration and src_fps else 0
        est_out = round(duration * target_fps) if duration else 0
        _disk_preflight(work, info["width"], info["height"], est_in, est_out)

        _u(job_id, stage="extracting", progress=20)
        frames_in = work / "in"
        n_in = ffmpeg.extract_frames(str(input_path), str(frames_in), s.interp_timeout_seconds)
        if n_in < 2:
            raise RuntimeError("need at least 2 frames to interpolate")

        # Total output frames for the whole clip at the target fps. Falls back to
        # n_in/src_fps when the container duration is missing.
        span = duration or (n_in / max(src_fps, 1e-6))
        num_out = max(2, round(span * target_fps))

        _u(job_id, stage="interpolating", progress=40)
        frames_out = work / "out"
        frames_out.mkdir(parents=True, exist_ok=True)

        def _rife_progress(done: int, total: int) -> None:
            # Fold the interpolation into the 40-78% band of the overall bar.
            if total:
                _u(job_id, progress=min(78, 40 + int(38 * done / total)))

        engine.run_rife(
            str(frames_in), str(frames_out), num_out, s.interp_timeout_seconds,
            on_progress=_rife_progress,
        )
        produced = len(list(frames_out.glob("*.png")))

        _u(job_id, stage="encoding", progress=80)
        out_path = work / "interpolated.mp4"
        ffmpeg.encode(
            str(frames_out), str(out_path), target_fps,
            audio_from=str(input_path), has_audio=info["has_audio"],
            timeout=s.interp_timeout_seconds,
        )

        _u(job_id, stage="uploading", progress=95)
        s3.upload(out_bucket, out_key, str(out_path))

        elapsed = time.monotonic() - started
        _u(
            job_id, status="done", stage="done", progress=100,
            output={
                "s3_bucket": out_bucket, "s3_key": out_key,
                "fps": target_fps, "frames": produced or num_out,
            },
            elapsed=elapsed, gpu=gpu,
        )
        IOF_JOBS_TOTAL.labels(status="done").inc()
        IOF_JOB_DURATION.observe(elapsed)
    except Exception as exc:  # noqa: BLE001 - surface as a failed job, never crash
        _u(job_id, status="failed", detail=str(exc)[:400], elapsed=time.monotonic() - started)
        IOF_JOBS_TOTAL.labels(status="failed").inc()
    finally:
        shutil.rmtree(work, ignore_errors=True)
