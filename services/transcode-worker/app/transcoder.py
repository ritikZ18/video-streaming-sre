from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List

from app.config import get_settings
from app.profiles import EncodingProfile, PROFILES

# Output artifact names produced by the ffmpeg dash muxer.
DASH_MANIFEST = "manifest.mpd"
HLS_MASTER = "master.m3u8"

# Segment duration in seconds (Apple's recommended HLS default; also used for DASH).
SEGMENT_DURATION = 6


def build_ffmpeg_command(
    input_path: Path,
    output_dir: Path,
    profiles: List[EncodingProfile] | None = None,
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

    # 2) Map each scaled video branch, then the audio once.
    for i in range(len(profiles)):
        cmd += ["-map", f"[v{i}out]"]
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

    cmd += [
        "-c:a",
        "aac",
        "-b:a",
        profiles[-1].audio_bitrate,
        "-ar",
        "48000",
    ]

    # 5) DASH muxer with CMAF segments; also emit HLS playlists from the same
    #    segments. Video streams form adaptation set 0, audio set 1.
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
        "id=0,streams=v id=1,streams=a",
        "-hls_playlist",
        "1",
        str(output_dir / DASH_MANIFEST),
    ]
    return cmd


def transcode_to_cmaf(input_path: Path, work_dir: Path) -> Dict[str, Path]:
    """
    Transcode ``input_path`` into a CMAF ABR ladder and return the paths of the
    generated HLS master playlist and DASH manifest.

    Both manifests plus all shared ``.m4s`` segments are written into
    ``work_dir`` and are meant to be uploaded verbatim to object storage.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_ffmpeg_command(input_path, work_dir)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg transcode failed: {result.stderr}")

    hls_master = work_dir / HLS_MASTER
    dash_manifest = work_dir / DASH_MANIFEST
    if not hls_master.exists() or not dash_manifest.exists():
        raise RuntimeError(
            "ffmpeg did not produce expected manifests "
            f"(hls={hls_master.exists()}, dash={dash_manifest.exists()})"
        )

    return {"hls": hls_master, "dash": dash_manifest}
