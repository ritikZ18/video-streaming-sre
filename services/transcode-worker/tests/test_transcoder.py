from pathlib import Path

from app.profiles import PROFILES
from app.transcoder import build_rendition_command


def test_rendition_command_encodes_scaled_video_with_audio(tmp_path: Path) -> None:
    profile = PROFILES[0]
    cmd = build_rendition_command(
        tmp_path / "in.mp4", tmp_path / "out.mp4", profile, include_audio=True
    )
    joined = " ".join(cmd)

    assert cmd[0] == "ffmpeg"
    assert "-progress" in cmd  # per-rendition progress
    assert f"scale={profile.width}:{profile.height}" in joined
    assert "libx264" in cmd  # CPU default (USE_NVENC off)
    assert profile.video_bitrate in cmd
    assert "0:a:0" in cmd  # audio mapped for the first rendition


def test_rendition_command_omits_audio_when_excluded(tmp_path: Path) -> None:
    profile = PROFILES[1]
    cmd = build_rendition_command(
        tmp_path / "in.mp4", tmp_path / "out.mp4", profile, include_audio=False
    )
    assert "-an" in cmd
    assert "0:a:0" not in cmd
