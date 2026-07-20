from pathlib import Path

from app.profiles import PROFILES
from app.transcoder import DASH_MANIFEST, build_ffmpeg_command


def test_build_ffmpeg_command_emits_both_hls_and_dash(tmp_path: Path) -> None:
    input_path = tmp_path / "in.mp4"
    output_dir = tmp_path / "out"
    cmd = build_ffmpeg_command(input_path, output_dir)

    assert "ffmpeg" in cmd[0]
    assert str(input_path) in cmd
    # Single DASH muxer output...
    assert "dash" in cmd
    assert str(output_dir / DASH_MANIFEST) in cmd
    # ...that also publishes HLS playlists from the same CMAF segments.
    assert "-hls_playlist" in cmd
    assert "1" in cmd


def test_build_ffmpeg_command_covers_every_rendition(tmp_path: Path) -> None:
    cmd = build_ffmpeg_command(tmp_path / "in.mp4", tmp_path / "out")
    joined = " ".join(cmd)

    # One split branch + bitrate entry per profile in the ladder.
    assert f"split={len(PROFILES)}" in joined
    for i, profile in enumerate(PROFILES):
        assert f"scale={profile.width}:{profile.height}" in joined
        assert f"-b:v:{i}" in cmd
        assert profile.video_bitrate in cmd
