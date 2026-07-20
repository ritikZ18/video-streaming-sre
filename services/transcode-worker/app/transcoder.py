from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List

from app.config import get_settings
from app.profiles import EncodingProfile, PROFILES

# Output artifact names produced by the ffmpeg dash muxer.
DASH_MANIFEST = "manifest.mpd"
HLS_MASTER = "master.m3u8"

# Segment duration in seconds (Apple's recommended HLS default; also used for DASH).
SEGMENT_DURATION = 6


def extract_thumbnail(input_path: Path, output_path: Path, at_seconds: float = 3.0) -> bool:
    """Grab a single poster frame at ``at_seconds`` (scaled to 640px wide)."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            str(at_seconds),
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=640:-2",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and output_path.exists()


def probe_duration(input_path: Path) -> float | None:
    """Return the media duration in seconds (via ffprobe), or None."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def has_audio_stream(input_path: Path) -> bool:
    """Return True if the input has at least one audio stream (via ffprobe)."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(input_path),
        ],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def build_ffmpeg_command(
    input_path: Path,
    output_dir: Path,
    profiles: List[EncodingProfile] | None = None,
    has_audio: bool = True,
) -> List[str]:
    """
    Build a single ffmpeg command that produces a CMAF (fMP4) ABR ladder and
    publishes **both** an HLS playlist set and a DASH manifest from the *same*
    segments.

    We encode every rendition once into fMP4/CMAF segments, then let ffmpeg's
    ``dash`` muxer emit ``manifest.mpd`` while ``-hls_playlist 1`` emits
    ``master.m3u8`` (+ per-rendition media playlists) that reference the exact
    same ``.m4s`` segments. This is the "package once, serve HLS and DASH"
    pattern and is why only one transcode pass is needed.

    Assumes the input has a single audio stream (true for standard uploads);
    the audio is encoded once into its own DASH adaptation set / HLS group.
    """
    profiles = profiles or PROFILES
    settings = get_settings()

    # 1) Split the source video into one branch per rendition and scale each.
    split_labels = "".join(f"[v{i}]" for i in range(len(profiles)))
    filter_parts = [f"[0:v]split={len(profiles)}{split_labels}"]
    for i, profile in enumerate(profiles):
        # format=yuv420p forces 4:2:0 chroma so H.264 main/high profiles and
        # every browser/device can decode it, regardless of source pixel format.
        filter_parts.append(
            f"[v{i}]scale={profile.width}:{profile.height},format=yuv420p[v{i}out]"
        )
    filter_complex = ";".join(filter_parts)

    cmd: List[str] = [
        "ffmpeg",
        "-y",
        "-threads",
        str(settings.ffmpeg_threads),
        "-i",
        str(input_path),
        "-filter_complex",
        filter_complex,
    ]

    # 2) Map each scaled video branch, then the audio once (if present).
    for i in range(len(profiles)):
        cmd += ["-map", f"[v{i}out]"]
    if has_audio:
        cmd += ["-map", "0:a:0"]

    # 3) Shared video/audio codec settings.
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-sc_threshold",
        "0",
        # Force a keyframe every SEGMENT_DURATION seconds so DASH/HLS segment
        # boundaries align across every rendition (fps-independent).
        "-force_key_frames",
        f"expr:gte(t,n_forced*{SEGMENT_DURATION})",
    ]

    # 4) Per-rendition bitrate ladder.
    for i, profile in enumerate(profiles):
        cmd += [
            f"-b:v:{i}",
            profile.video_bitrate,
            f"-maxrate:v:{i}",
            profile.maxrate,
            f"-bufsize:v:{i}",
            profile.bufsize,
            f"-profile:v:{i}",
            profile.profile,
        ]

    if has_audio:
        cmd += [
            "-c:a",
            "aac",
            "-b:a",
            profiles[-1].audio_bitrate,
            "-ar",
            "48000",
        ]

    # 5) DASH muxer with CMAF segments; also emit HLS playlists from the same
    #    segments. Video streams form adaptation set 0, audio (if any) set 1.
    adaptation_sets = "id=0,streams=v id=1,streams=a" if has_audio else "id=0,streams=v"
    cmd += [
        "-f",
        "dash",
        "-seg_duration",
        str(SEGMENT_DURATION),
        "-use_template",
        "1",
        "-use_timeline",
        "1",
        "-adaptation_sets",
        adaptation_sets,
        "-hls_playlist",
        "1",
        str(output_dir / DASH_MANIFEST),
    ]
    return cmd


def transcode_to_cmaf(
    input_path: Path,
    work_dir: Path,
    on_progress: Callable[[int], None] | None = None,
) -> Dict[str, Path]:
    """
    Transcode ``input_path`` into a CMAF ABR ladder and return the paths of the
    generated HLS master playlist and DASH manifest.

    If ``on_progress`` is given it is called with an integer percentage (0-99)
    as ffmpeg advances, computed from ffmpeg's ``-progress`` output against the
    probed total duration. Both manifests plus all shared ``.m4s`` segments are
    written into ``work_dir`` for verbatim upload to object storage.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    total = probe_duration(input_path) or 0.0
    cmd = build_ffmpeg_command(input_path, work_dir, has_audio=has_audio_stream(input_path))
    # Stream machine-readable progress on stdout; keep stderr in a temp file so
    # a full stderr pipe can never deadlock the stdout reader on long encodes.
    cmd = [cmd[0], "-progress", "pipe:1", "-nostats", *cmd[1:]]

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
                pct = min(99, int((out_us / 1_000_000) / total * 100))
                on_progress(pct)
        proc.wait()
        if proc.returncode != 0:
            err_file.seek(0)
            raise RuntimeError(f"ffmpeg transcode failed: {err_file.read()}")

    hls_master = work_dir / HLS_MASTER
    dash_manifest = work_dir / DASH_MANIFEST
    if not hls_master.exists() or not dash_manifest.exists():
        raise RuntimeError(
            "ffmpeg did not produce expected manifests "
            f"(hls={hls_master.exists()}, dash={dash_manifest.exists()})"
        )

    return {"hls": hls_master, "dash": dash_manifest}
