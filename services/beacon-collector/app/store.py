"""In-memory rolling QoE aggregation for the live admin dashboard.

Prometheus (persistent) keeps the long-term history for Grafana; this store keeps
a short rolling window of raw sessions/events so the admin UI can show live
Quality-of-Experience numbers (startup percentiles, rebuffer ratio, error rate,
bitrate, per-title breakdown) without running PromQL in the browser.

Bounded and self-pruning, so memory stays flat. A single lock guards the state —
ingest volume here is tiny (one batch per player, every ~15s).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

# Keep a rolling window; anything older is pruned on read.
WINDOW_SECONDS = 1800  # 30 min
ACTIVE_SECONDS = 45  # a session seen within this is "active" (heartbeat is 15s)
MAX_EVENTS = 3000  # hard cap on the recent-events ring


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (pct in 0..1). Returns 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(pct * (len(ordered) - 1)))))
    return ordered[k]


class QoEStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # session_id -> aggregate
        self._sessions: dict[str, dict[str, Any]] = {}
        # recent raw events (for the live feed)
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)

    def record(self, batch: Any) -> None:
        """Fold one beacon batch into the rolling store."""
        now = time.time()
        with self._lock:
            s = self._sessions.get(batch.session_id)
            if s is None:
                s = {
                    "first_seen": now,
                    "content_id": batch.content_id,
                    "player_version": batch.player_version,
                    "startup_ms": None,
                    "rebuffers": 0,
                    "rebuffer_ms": 0.0,
                    "errors": 0,
                    "last_bitrate_kbps": None,
                }
                self._sessions[batch.session_id] = s
            s["last_seen"] = now
            if batch.content_id:
                s["content_id"] = batch.content_id

            for ev in batch.events:
                detail = ""
                if ev.event == "startup" and ev.startup_ms is not None:
                    if s["startup_ms"] is None:
                        s["startup_ms"] = ev.startup_ms
                    detail = f"{ev.startup_ms} ms"
                elif ev.event == "rebuffer" and ev.rebuffer_ms is not None:
                    s["rebuffers"] += 1
                    s["rebuffer_ms"] += ev.rebuffer_ms
                    detail = f"{ev.rebuffer_ms} ms"
                elif ev.event == "bitrate_switch" and ev.current_bitrate_kbps is not None:
                    s["last_bitrate_kbps"] = ev.current_bitrate_kbps
                    detail = f"{ev.current_bitrate_kbps} kbps"
                elif ev.event == "heartbeat" and ev.current_bitrate_kbps is not None:
                    s["last_bitrate_kbps"] = ev.current_bitrate_kbps
                    detail = f"{ev.current_bitrate_kbps} kbps"
                elif ev.event == "error" and ev.error_type:
                    s["errors"] += 1
                    detail = ev.error_type
                self._events.append(
                    {
                        "ts": now,
                        "session_id": batch.session_id,
                        "content_id": batch.content_id,
                        "event": ev.event,
                        "detail": detail,
                    }
                )

    def _prune(self, now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        stale = [sid for sid, s in self._sessions.items() if s.get("last_seen", 0) < cutoff]
        for sid in stale:
            del self._sessions[sid]

    def stats(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._prune(now)
            sessions = list(self._sessions.values())
            events = [e for e in self._events if e["ts"] >= now - WINDOW_SECONDS]

        total = len(sessions)
        active = sum(1 for s in sessions if s.get("last_seen", 0) >= now - ACTIVE_SECONDS)
        startup_vals = [float(s["startup_ms"]) for s in sessions if s.get("startup_ms") is not None]
        rebuffered = [s for s in sessions if s["rebuffers"] > 0]
        rebuffer_events = sum(s["rebuffers"] for s in sessions)
        rebuffer_ms_total = sum(s["rebuffer_ms"] for s in sessions)
        bitrates = [float(s["last_bitrate_kbps"]) for s in sessions if s.get("last_bitrate_kbps")]
        errors_total = sum(s["errors"] for s in sessions)

        # Errors by type from the recent event feed.
        by_type: dict[str, int] = {}
        for e in events:
            if e["event"] == "error" and e["detail"]:
                by_type[e["detail"]] = by_type.get(e["detail"], 0) + 1

        # Per-title breakdown.
        by_content: dict[str, dict[str, Any]] = {}
        for s in sessions:
            cid = s.get("content_id") or "unknown"
            c = by_content.setdefault(cid, {"sessions": 0, "startups": [], "rebuffered": 0})
            c["sessions"] += 1
            if s.get("startup_ms") is not None:
                c["startups"].append(float(s["startup_ms"]))
            if s["rebuffers"] > 0:
                c["rebuffered"] += 1
        top_content = sorted(
            (
                {
                    "content_id": cid,
                    "sessions": c["sessions"],
                    "startup_p95_ms": round(_percentile(c["startups"], 0.95)),
                    "rebuffer_ratio": round(c["rebuffered"] / c["sessions"], 3) if c["sessions"] else 0,
                }
                for cid, c in by_content.items()
            ),
            key=lambda x: x["sessions"],
            reverse=True,
        )[:8]

        recent = [
            {
                "ts": e["ts"],
                "session_id": e["session_id"][:8],
                "content_id": e["content_id"],
                "event": e["event"],
                "detail": e["detail"],
            }
            for e in list(reversed(events))[:25]
        ]

        return {
            "window_seconds": WINDOW_SECONDS,
            "generated_at": now,
            "sessions": {
                "total": total,
                "active": active,
                "rebuffer_free_pct": round(100.0 * (total - len(rebuffered)) / total, 1) if total else 100.0,
            },
            "startup_ms": {
                "count": len(startup_vals),
                "p50": round(_percentile(startup_vals, 0.50)),
                "p95": round(_percentile(startup_vals, 0.95)),
                "avg": round(sum(startup_vals) / len(startup_vals)) if startup_vals else 0,
            },
            "rebuffer": {
                "events": rebuffer_events,
                "sessions_affected": len(rebuffered),
                "avg_ms": round(rebuffer_ms_total / rebuffer_events) if rebuffer_events else 0,
                "ratio": round(len(rebuffered) / total, 3) if total else 0.0,
            },
            "bitrate_kbps": {
                "avg": round(sum(bitrates) / len(bitrates)) if bitrates else 0,
                "p50": round(_percentile(bitrates, 0.50)),
            },
            "errors": {"total": errors_total, "by_type": by_type},
            "top_content": top_content,
            "recent_events": recent,
        }


store = QoEStore()
