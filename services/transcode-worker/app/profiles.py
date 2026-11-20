from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EncodingProfile:
    name: str
    width: int
    height: int
    video_bitrate: str
    maxrate: str
    bufsize: str
    audio_bitrate: str
    profile: str


PROFILES: list[EncodingProfile] = [
    EncodingProfile(
        name="360p",
        width=640,
        height=360,
        video_bitrate="800k",
        maxrate="856k",
        bufsize="1200k",
        audio_bitrate="128k",
        profile="main",
    ),
    EncodingProfile(
        name="720p",
        width=1280,
        height=720,
        video_bitrate="2500k",
        maxrate="2675k",
        bufsize="3750k",
        audio_bitrate="128k",
        profile="main",
    ),
    EncodingProfile(
        name="1080p",
        width=1920,
        height=1080,
        video_bitrate="5000k",
        maxrate="5350k",
        bufsize="7500k",
        audio_bitrate="192k",
        profile="high",
    ),
    EncodingProfile(
        name="1440p",
        width=2560,
        height=1440,
        video_bitrate="12000k",
        maxrate="12840k",
        bufsize="18000k",
        audio_bitrate="192k",
        profile="high",
    ),
    EncodingProfile(
        name="2160p",
        width=3840,
        height=2160,
        video_bitrate="24000k",
        maxrate="25680k",
        bufsize="36000k",
        audio_bitrate="192k",
        profile="high",
    ),
]


def ladder_for(source_height: int) -> "list[EncodingProfile]":
    """Rungs to encode for a source of the given height. Never upscale (only
    rungs <= the source), but always keep at least the lowest rung so a tiny
    source still produces a playable stream. A 4K source therefore yields the
    full 360p→2160p ladder; a 1080p source stops at 1080p."""
    if source_height <= 0:
        return [p for p in PROFILES if p.height <= 1080]
    usable = [p for p in PROFILES if p.height <= source_height]
    return usable or [PROFILES[0]]


