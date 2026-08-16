"""Per-channel live ffmpeg process lifecycle: start, monitor, stop.

Each live channel is one long-running ffmpeg writing a rolling HLS window. We
track the process, tail its progress (fps / speed-vs-realtime) for metrics, and
clean up its segment directory on stop. A GTX-1650-sized box only wants one
channel at a time, so the manager enforces a hard cap.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from prometheus_client import Gauge

logger = logging.getLogger("live-packager")

# --- Metrics (per channel; the label is the event id) ---------------------
LIVE_UP = Gauge("live_channel_up", "1 while a live channel is encoding", ["event"])
LIVE_FPS = Gauge("live_encoder_fps", "Live encoder output frames per second", ["event"])
LIVE_SPEED = Gauge(
    "live_encoder_speed_ratio",
    "Encoder speed vs realtime (>=1.0 means the encoder is keeping up)",
    ["event"],
)
LIVE_ACTIVE = Gauge("live_active_channels", "Number of active live channels")


@dataclass
class Channel:
    event_id: str
    kind: str  # "playout" | "ingest" | "test"
    out_dir: str
    proc: subprocess.Popen
    started_at: float
    fps: float = 0.0
    speed: float = 0.0
    stopping: bool = False
    stderr_tail: deque = field(default_factory=lambda: deque(maxlen=25))

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    @property
    def uptime(self) -> float:
        return round(time.time() - self.started_at, 1)


class ChannelLimitError(RuntimeError):
    pass


class ChannelManager:
    def __init__(self, max_channels: int) -> None:
        self._max = max_channels
        self._channels: dict[str, Channel] = {}
        self._lock = threading.Lock()

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for c in self._channels.values() if c.alive)

    def get(self, event_id: str) -> Channel | None:
        with self._lock:
            return self._channels.get(event_id)

    def start(self, event_id: str, cmd: list[str], out_dir: str, kind: str) -> Channel:
        with self._lock:
            existing = self._channels.get(event_id)
            if existing and existing.alive:
                return existing  # idempotent: already streaming this event
            active = sum(1 for c in self._channels.values() if c.alive)
            if active >= self._max:
                raise ChannelLimitError(
                    f"Live channel limit reached ({self._max}); stop another channel first."
                )

            # Fresh output dir so a previous session's segments never linger.
            shutil.rmtree(out_dir, ignore_errors=True)
            os.makedirs(out_dir, exist_ok=True)

            logger.info("starting %s channel %s: %s", kind, event_id, " ".join(cmd))
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            channel = Channel(
                event_id=event_id, kind=kind, out_dir=out_dir,
                proc=proc, started_at=time.time(),
            )
            self._channels[event_id] = channel

        LIVE_UP.labels(event_id).set(1)
        LIVE_ACTIVE.set(self.running_count())
        threading.Thread(target=self._watch_progress, args=(channel,), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(channel,), daemon=True).start()
        return channel

    def stop(self, event_id: str, clean: bool = True) -> bool:
        with self._lock:
            channel = self._channels.pop(event_id, None)
        if channel is None:
            return False
        channel.stopping = True
        proc = channel.proc
        if proc.poll() is None:
            try:
                proc.send_signal(signal.SIGINT)  # let ffmpeg flush the playlist
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception:  # noqa: BLE001
                proc.kill()
        self._reset_metrics(event_id)
        if clean:
            shutil.rmtree(channel.out_dir, ignore_errors=True)
        LIVE_ACTIVE.set(self.running_count())
        return True

    # --- monitor threads --------------------------------------------------
    def _watch_progress(self, channel: Channel) -> None:
        """Parse ffmpeg's -progress stream (key=value lines) for fps/speed."""
        proc = channel.proc
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("fps="):
                    channel.fps = _to_float(line[4:])
                    LIVE_FPS.labels(channel.event_id).set(channel.fps)
                elif line.startswith("speed="):
                    channel.speed = _to_float(line[6:].rstrip("x"))
                    LIVE_SPEED.labels(channel.event_id).set(channel.speed)
        except Exception:  # noqa: BLE001 - the pipe closes when ffmpeg exits
            pass
        finally:
            code = proc.wait()
            if not channel.stopping:
                logger.warning(
                    "live channel %s exited unexpectedly (code=%s): %s",
                    channel.event_id, code, " | ".join(channel.stderr_tail),
                )
            self._reset_metrics(channel.event_id)
            with self._lock:
                # Only drop it if this exact process is still the registered one.
                current = self._channels.get(channel.event_id)
                if current is channel:
                    self._channels.pop(channel.event_id, None)
            LIVE_ACTIVE.set(self.running_count())

    def _drain_stderr(self, channel: Channel) -> None:
        proc = channel.proc
        try:
            assert proc.stderr is not None
            for line in proc.stderr:
                line = line.strip()
                if line:
                    channel.stderr_tail.append(line)
        except Exception:  # noqa: BLE001
            pass

    def _reset_metrics(self, event_id: str) -> None:
        for gauge in (LIVE_UP, LIVE_FPS, LIVE_SPEED):
            try:
                gauge.labels(event_id).set(0)
            except Exception:  # noqa: BLE001
                pass


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
