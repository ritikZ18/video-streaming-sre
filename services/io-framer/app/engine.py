from __future__ import annotations

import re
import subprocess

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


def run_rife(frames_in: str, frames_out: str, num_frames: int, timeout: int) -> None:
    """Interpolate the frames in ``frames_in`` to ``num_frames`` total frames in
    ``frames_out`` using rife-ncnn-vulkan. ``-n`` makes v4.x emit an arbitrary
    output frame count (not just 2×)."""
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
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"rife failed: {(p.stderr or p.stdout)[-400:]}")
