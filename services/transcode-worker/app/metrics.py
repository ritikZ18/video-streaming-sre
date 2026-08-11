from prometheus_client import Counter, Gauge, Histogram, start_http_server

TRANSCODE_JOBS_TOTAL = Counter(
    "transcode_jobs_total",
    "Total transcode jobs processed",
    ["status"],
)

TRANSCODE_JOB_DURATION = Histogram(
    "transcode_job_duration_seconds",
    "Transcode job duration seconds",
    buckets=(10, 30, 60, 120, 300, 600, 900),
)

QUEUE_DEPTH = Gauge(
    "transcode_queue_depth",
    "Approximate number of messages visible in the transcode queue",
)

SEGMENTS_UPLOADED = Counter(
    "transcode_segments_uploaded_total",
    "Total number of HLS segments uploaded",
)

# Frame interpolation (I/O Framer) outcomes as seen by the worker: done (a
# higher-fps ladder published), skipped (a guardrail declined it) or failed (the
# sidecar errored / was unreachable → native-fps fallback).
INTERP_JOBS_TOTAL = Counter(
    "interp_jobs_total",
    "Frame-interpolation outcomes",
    ["result"],
)

INTERP_DURATION = Histogram(
    "interp_duration_seconds",
    "Wall-clock of a completed interpolation pass (worker-observed)",
    buckets=(15, 30, 60, 120, 300, 600, 1200, 1800),
)


def start_metrics_server(port: int = 9100) -> None:
    """Start Prometheus metrics HTTP server."""
    start_http_server(port)


