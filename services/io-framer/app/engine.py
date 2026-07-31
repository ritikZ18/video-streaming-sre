from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Callable

from app.config import get_settings


def detect_backend() -> tuple[str, bool, list[str]]:
    """Enumerate Vulkan devices and classify the backend.

    Returns ``(backend, gpu, device_names)`` where backend is:
      - ``"vulkan"`` — a real GPU is present (hardware acceleration)
      - ``"cpu"``    — only a software rasterizer (lavapipe/llvmpipe) is present
      - ``"none"``   — no Vulkan device at all
    """
    names: list[str] = []
    try:
        p = subprocess.run(
            ["vulkaninfo", "--summary"], capture_output=True, text=True, timeout=20
        )
        for m in re.finditer(r"deviceName\s*=\s*(.+)", p.stdout):
            names.append(m.group(1).strip())
    except Exception:  # noqa: BLE001 - missing loader/tool → treat as no device
        names = []
    if not names:
        return "none", False, []
    software = all(
        "llvmpipe" in n.lower() or "lavapipe" in n.lower() for n in names
    )
    return ("cpu", False, names) if software else ("vulkan", True, names)


def run_rife(
    frames_in: str,
    frames_out: str,
    num_frames: int,
    timeout: int,
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """Interpolate the frames in ``frames_in`` to ``num_frames`` total frames in
    ``frames_out`` using rife-ncnn-vulkan. ``-n`` makes v4.x emit an arbitrary
    output frame count (not just 2×).

    Runs under a hard wall-clock ``timeout`` (the binary has no self-timeout) and,
    if given ``on_progress``, reports ``(done, total)`` by counting the output
    frames as they land — the interpolation is the longest stage, so this drives
    the live progress bar."""
    s = get_settings()
    model_path = f"{s.rife_models_dir}/{s.rife_model}"
    cmd = [
        s.rife_bin,
        "-i", frames_in,
        "-o", frames_out,
        "-m", model_path,
        "-n", str(num_frames),
        "-g", str(s.gpu_id),
    ]
    out_dir = Path(frames_out)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    start = time.monotonic()
    while proc.poll() is None:
        if time.monotonic() - start > timeout:
            proc.kill()
            proc.wait(timeout=10)
            raise RuntimeError(f"rife timed out after {timeout}s")
        if on_progress is not None:
            try:
                on_progress(len(list(out_dir.glob("*.png"))), num_frames)
            except Exception:  # noqa: BLE001 - progress is best-effort
                pass
        time.sleep(2)
    _, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"rife failed: {(err or '')[-400:]}")
