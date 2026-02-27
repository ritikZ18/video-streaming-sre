from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.profiles import EncodingProfile, PROFILES


def generate_master_manifest(
    playlists: Iterable[Path],
    output_path: Path,
    profiles: list[EncodingProfile] | None = None,
) -> None:
    """
    Write an HLS master manifest referencing the given variant playlists.
    """
    profiles = profiles or PROFILES
    profile_by_name = {p.name: p for p in profiles}

    lines: list[str] = ["#EXTM3U", "#EXT-X-VERSION:7"]

    for playlist in playlists:
        name = playlist.stem
        profile = profile_by_name.get(name)
        if profile is None:
            continue
        bandwidth = _estimate_bandwidth(profile.video_bitrate, profile.audio_bitrate)
        codecs = "avc1.64001f,mp4a.40.2"
        lines.append(
            f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},'
            f'CODECS="{codecs}",RESOLUTION={profile.width}x{profile.height}',
        )
        lines.append(playlist.name)

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _estimate_bandwidth(video_bitrate: str, audio_bitrate: str) -> int:
    def to_kbps(value: str) -> int:
        if value.endswith("k"):
            return int(value[:-1])
        if value.endswith("M"):
            return int(float(value[:-1]) * 1000)
        return int(value)

    return (to_kbps(video_bitrate) + to_kbps(audio_bitrate)) * 1024


