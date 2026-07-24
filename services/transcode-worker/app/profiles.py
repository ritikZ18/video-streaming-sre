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
]


