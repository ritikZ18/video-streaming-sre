from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, List

from app.config import get_settings
from app.profiles import EncodingProfile, PROFILES


def build_ffmpeg_command(
    input_path: Path,
    output_dir: Path,
    profile: EncodingProfile,
) -> List[str]:
    """Return an ffmpeg command for a single HLS rendition."""
    segment_pattern = str(output_dir / f"{profile.name}_%03d.m4s")
    playlist_path = str(output_dir / f"{profile.name}.m3u8")
    settings = get_settings()

    return [
        "ffmpeg",
        "-y",
        "-threads",
        str(settings.ffmpeg_threads),
        "-i",
        str(input_path),
        "-vf",
        f"scale={profile.width}:{profile.height}",
        "-c:v",
        "libx264",
        "-b:v",
        profile.video_bitrate,
        "-maxrate",
        profile.maxrate,
        "-bufsize",
        profile.bufsize,
        "-profile:v",
        profile.profile,
        "-preset",
        "fast",
        "-c:a",
        "aac",
        "-b:a",
        profile.audio_bitrate,
        "-ar",
        "48000",
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_segment_type",
        "fmp4",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_filename",
        segment_pattern,
        playlist_path,
    ]


def transcode_to_hls(input_path: Path, work_dir: Path) -> Iterable[Path]:
    """
    Transcode the given input file into HLS renditions.

    Returns a list of generated playlist paths.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    playlists: list[Path] = []
    for profile in PROFILES:
        cmd = build_ffmpeg_command(input_path, work_dir, profile)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed for profile {profile.name}: {result.stderr}")
        playlists.append(work_dir / f"{profile.name}.m3u8")
    return playlists


