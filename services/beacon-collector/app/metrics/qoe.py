from prometheus_client import Counter, Histogram

QOE_STARTUP = Histogram(
    "qoe_startup_duration_seconds",
    "Video startup duration in seconds",
    buckets=(0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 8, 10, 15),
)

QOE_REBUFFER_EVENTS = Counter(
    "qoe_rebuffer_events_total",
    "Number of rebuffer events",
    ["region", "content_id"],
)

QOE_REBUFFER_DURATION = Histogram(
    "qoe_rebuffer_duration_seconds",
    "Total rebuffering duration in seconds",
    buckets=(0.5, 1, 2, 5, 10, 20, 30),
)

QOE_BITRATE_SWITCHES = Counter(
    "qoe_bitrate_switches_total",
    "Number of bitrate switches",
)

QOE_SESSIONS_TOTAL = Counter(
    "qoe_sessions_total",
    "Total playback sessions",
)

QOE_SESSIONS_NO_REBUFFER = Counter(
    "qoe_sessions_without_rebuffer_total",
    "Sessions that experienced no rebuffering",
)

QOE_ERRORS = Counter(
    "qoe_errors_total",
    "Client-side playback errors by type",
    ["error_type"],
)

QOE_SESSION_HEARTBEATS = Counter(
    "qoe_session_heartbeats_total",
    "Number of QoE heartbeat events",
)

