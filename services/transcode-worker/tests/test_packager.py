from pathlib import Path

from app.packager import _estimate_bandwidth, generate_master_manifest
from app.profiles import PROFILES


def test_estimate_bandwidth_combines_video_and_audio() -> None:
    bw = _estimate_bandwidth("1000k", "128k")
    # 1128 kbps * 1024
    assert bw == 1128 * 1024


def test_generate_master_manifest_contains_variants(tmp_path: Path) -> None:
    p360 = tmp_path / "360p.m3u8"
    p360.write_text("#EXTM3U\n", encoding="utf-8")
    p720 = tmp_path / "720p.m3u8"
    p720.write_text("#EXTM3U\n", encoding="utf-8")

    master = tmp_path / "master.m3u8"
    generate_master_manifest([p360, p720], master)

    content = master.read_text(encoding="utf-8")
    assert "360p.m3u8" in content
    assert "720p.m3u8" in content
    assert "RESOLUTION=640x360" in content or "RESOLUTION=1280x720" in content

