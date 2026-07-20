from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List

from app.config import get_settings
from app.profiles import EncodingProfile, PROFILES

# Output artifact names.
DASH_MANIFEST = "manifest.mpd"
HLS_MASTER = "master.m3u8"

# Segment duration in seconds (Apple's recommended HLS default; also used for DASH).
SEGMENT_DURATION = 6

ProgressCb = Callable[[int], None]


def has_audio_stream(input_path: Path) -> bool:
    """Return True if the input has at least one audio stream (via ffprobe)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(input_path)],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def probe_duration(input_path: Path) -> float | None:
    """Return the media duration in seconds (via ffprobe), or None."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(input_path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def extract_thumbnail(input_path: Path, output_path: Path, at_seconds: float = 3.0) -> bool:
    """Grab a single poster frame at ``at_seconds`` (scaled to 640px wide)."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at_seconds), "-i", str(input_path),
         "-frames:v", "1", "-vf", "scale=640:-2", str(output_path)],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and output_path.exists()


def _run_ffmpeg_progress(cmd: List[str], total: float, on_progress: ProgressCb | None) -> None:
    """Run ffmpeg, streaming -progress (out_time_us) into on_progress (0-100).

    stderr goes to a temp file so a full stderr pipe can't deadlock the reader.
    """
    with tempfile.TemporaryFile(mode="w+") as err_file:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err_file, text=True)
        if proc.stdout is not None:
            for raw in proc.stdout:
                line = raw.strip()
                if not (on_progress and total > 0 and line.startswith("out_time_us=")):
                    continue
                try:
                    out_us = max(0, int(line.split("=", 1)[1]))
                except ValueError:
                    continue
                on_progress(min(99, int((out_us / 1_000_000) / total * 100)))
        proc.wait()
        if proc.returncode != 0:
            err_file.seek(0)
            raise RuntimeError(f"ffmpeg failed: {err_file.read()}")


def build_rendition_command(
    input_path: Path,
    output_path: Path,
    profile: EncodingProfile,
    include_audio: bool,
) -> List[str]:
    """ffmpeg command to encode ONE rendition to an MP4 (with per-rendition progress).

    Uses NVENC + CUDA decode when USE_NVENC is set (GPU), else libx264 veryfast (CPU).
    """
    settings = get_settings()
    cmd: List[str] = [
        "ffmpeg", "-y", "-progress", "pipe:1", "-nostats", "-loglevel", "error",
    ]
    if settings.use_nvenc:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-threads", str(settings.ffmpeg_threads), "-i", str(input_path)]

    # format=yuv420p forces 4:2:0 so every browser/device can decode it.
    cmd += ["-vf", f"scale={profile.width}:{profile.height},format=yuv420p"]

    if settings.use_nvenc:
        cmd += [
            "-c:v", "h264_nvenc", "-preset", settings.nvenc_preset,
            "-b:v", profile.video_bitrate, "-maxrate", profile.maxrate,
            "-bufsize", profile.bufsize,
        ]
    else:
        cmd += [
            "-c:v", "libx264", "-preset", settings.x264_preset,
            "-b:v", profile.video_bitrate, "-maxrate", profile.maxrate,
            "-bufsize", profile.bufsize, "-profile:v", profile.profile,
        ]

    # Align keyframes to segment boundaries so all renditions cut at the same points.
    cmd += ["-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_DURATION})", "-sc_threshold", "0"]

    if include_audio:
        cmd += ["-map", "0:v:0", "-map", "0:a:0",
                "-c:a", "aac", "-b:a", profile.audio_bitrate, "-ar", "48000"]
    else:
        cmd += ["-map", "0:v:0", "-an"]

    cmd += ["-movflags", "+faststart", str(output_path)]
    return cmd


def encode_rendition(
    input_path: Path,
    output_path: Path,
    profile: EncodingProfile,
    include_audio: bool,
    total_seconds: float,
    on_progress: ProgressCb | None = None,
) -> Path:
    """Encode a single rendition MP4, reporting 0-100 progress for THIS rendition."""
    cmd = build_rendition_command(input_path, output_path, profile, include_audio)
    _run_ffmpeg_progress(cmd, total_seconds, on_progress)
    return output_path


def package_cmaf(rendition_paths: List[Path], work_dir: Path, has_audio: bool) -> Dict[str, Path]:
    """Stream-copy the per-rendition MP4s into ONE CMAF set: master.m3u8 + manifest.mpd.

    No re-encode (``-c copy``), so this is fast. Audio is taken from the first
    rendition; video streams from all of them form the ABR ladder.
    """
    cmd: List[str] = ["ffmpeg", "-y", "-loglevel", "error"]
    for path in rendition_paths:
        cmd += ["-i", str(path)]
    for i in range(len(rendition_paths)):
        cmd += ["-map", f"{i}:v:0"]
    if has_audio:
        cmd += ["-map", "0:a:0"]
    cmd += ["-c", "copy"]

    adaptation = "id=0,streams=v id=1,streams=a" if has_audio else "id=0,streams=v"
    cmd += [
        "-f", "dash", "-seg_duration", str(SEGMENT_DURATION),
        "-use_template", "1", "-use_timeline", "1",
        "-adaptation_sets", adaptation, "-hls_playlist", "1",
        str(work_dir / DASH_MANIFEST),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"packaging failed: {result.stderr}")

    hls_master = work_dir / HLS_MASTER
    dash_manifest = work_dir / DASH_MANIFEST
    if not hls_master.exists() or not dash_manifest.exists():
        raise RuntimeError(
            f"packaging did not produce manifests (hls={hls_master.exists()}, "
            f"dash={dash_manifest.exists()})"
        )
    return {"hls": hls_master, "dash": dash_manifest}
