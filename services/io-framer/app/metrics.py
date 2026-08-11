from prometheus_client import Counter, Histogram

# Terminal outcomes of an interpolation pass, as seen by the sidecar itself.
IOF_JOBS_TOTAL = Counter(
    "iof_jobs_total",
    "I/O Framer interpolation jobs by terminal status",
    ["status"],
)

IOF_JOB_DURATION = Histogram(
    "iof_job_duration_seconds",
    "End-to-end pass duration (download + decode + RIFE + encode + upload)",
    buckets=(15, 30, 60, 120, 300, 600, 1200, 1800),
)
