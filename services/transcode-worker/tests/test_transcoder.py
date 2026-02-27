from pathlib import Path

from app.profiles import PROFILES
from app.transcoder import build_ffmpeg_command


def test_build_ffmpeg_command_uses_profile_name_and_paths(tmp_path: Path) -> None:
    profile = PROFILES[0]
    input_path = tmp_path / "in.mp4"
    output_dir = tmp_path / "out"
    cmd = build_ffmpeg_command(input_path, output_dir, profile)

    assert "ffmpeg" in cmd[0]
    assert str(input_path) in cmd
    assert str(output_dir / f"{profile.name}.m3u8") in cmd

