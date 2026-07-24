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


def start_metrics_server(port: int = 9100) -> None:
    """Start Prometheus metrics HTTP server."""
    start_http_server(port)


