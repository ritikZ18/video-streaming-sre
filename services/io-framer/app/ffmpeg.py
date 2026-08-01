from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _fps(rate: str | None) -> float:
    """Parse an ffprobe frame-rate string like '24000/1001' → 23.976."""
    if not rate or "/" not in rate:
        return 0.0
    try:
        num, den = rate.split("/")
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    except ValueError:
        return 0.0


def probe(path: str) -> dict:
    p = _run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_streams", "-show_format", path,
        ]
    )
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {p.stderr[:300]}")
    data = json.loads(p.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v:
        raise RuntimeError("no video stream")
    fps = _fps(v.get("avg_frame_rate")) or _fps(v.get("r_frame_rate"))
    duration = float(data.get("format", {}).get("duration") or v.get("duration") or 0.0)
    return {
        "fps": fps,
        "duration": duration,
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "has_audio": a is not None,
    }


def extract_frames(
    input_path: str, frames_dir: str, timeout: int, scale_height: int | None = None
) -> int:
    """Decode every source frame to a lossless PNG. Returns the frame count.

    ``scale_height`` (when set) downscales each frame to that height first — so a
    4K source can be interpolated at, say, 1080p for far less disk/time. Width is
    auto (``-2``, kept even); this only ever shrinks (the caller passes a height
    below the source)."""
    Path(frames_dir).mkdir(parents=True, exist_ok=True)
    # -fps_mode passthrough keeps every source frame (1:1); no frame dropping.
    cmd = ["ffmpeg", "-y", "-i", input_path, "-fps_mode", "passthrough"]
    if scale_height:
        cmd += ["-vf", f"scale=-2:{scale_height}:flags=lanczos"]
    cmd += [f"{frames_dir}/frame_%08d.png"]
    p = _run(cmd, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"frame extract failed: {p.stderr[-300:]}")
    return len(list(Path(frames_dir).glob("frame_*.png")))


def encode(
    frames_dir: str,
    out_path: str,
    fps: int,
    audio_from: str | None,
    has_audio: bool,
    timeout: int,
) -> None:
    """Encode the interpolated PNG sequence at the target fps into an H.264
    mezzanine, carrying the original audio (which is unchanged) if present.

    Uses a glob input rather than a numbered pattern: rife-ncnn-vulkan writes its
    frames as zero-padded ``00000001.png`` (no prefix), which sort correctly, so a
    glob is robust to the exact naming."""
    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps),
        "-pattern_type", "glob", "-i", f"{frames_dir}/*.png",
    ]
    if has_audio and audio_from:
        cmd += [
            "-i", audio_from,
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
        ]
    else:
        cmd += ["-map", "0:v:0"]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "16",
        "-pix_fmt", "yuv420p", out_path,
    ]
    p = _run(cmd, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"encode failed: {p.stderr[-300:]}")
