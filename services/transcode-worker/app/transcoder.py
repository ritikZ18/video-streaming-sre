from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List

from app.config import get_settings
from app.profiles import EncodingProfile, PROFILES

# Subtitle codecs we can convert to WebVTT (text-based). Image subs (PGS/VobSub)
# are detected but not converted (would need OCR).
TEXT_SUBTITLE_CODECS = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}

# Minimal ISO-639-2 -> display name for nicer audio/subtitle labels.
LANG_NAMES = {
    "eng": "English", "spa": "Spanish", "fre": "French", "fra": "French",
    "ger": "German", "deu": "German", "hin": "Hindi", "jpn": "Japanese",
    "kor": "Korean", "chi": "Chinese", "zho": "Chinese", "ita": "Italian",
    "por": "Portuguese", "rus": "Russian", "ara": "Arabic", "und": "Undetermined",
}


def lang_name(code: str | None) -> str:
    if not code:
        return "Undetermined"
    return LANG_NAMES.get(code.lower(), code.upper())

# Output artifact names.
DASH_MANIFEST = "manifest.mpd"
HLS_MASTER = "master.m3u8"

# Segment duration in seconds (Apple's recommended HLS default; also used for DASH).
SEGMENT_DURATION = 6

ProgressCb = Callable[[int], None]


def has_audio_stream(input_path: Path) -> bool:
    """Return True if the input has at least one audio stream (via ffprobe)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(input_path)],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def probe_duration(input_path: Path) -> float | None:
    """Return the media duration in seconds (via ffprobe), or None."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(input_path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def extract_thumbnail(input_path: Path, output_path: Path, at_seconds: float = 3.0) -> bool:
    """Grab a single poster frame at ``at_seconds`` (scaled to 640px wide)."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at_seconds), "-i", str(input_path),
         "-frames:v", "1", "-vf", "scale=640:-2", str(output_path)],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and output_path.exists()


def probe_media(input_path: Path) -> Dict[str, Any]:
    """Full ffprobe (the 'VLC' metadata): video + audio tracks + subtitle tracks."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(input_path)],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        data = {}

    info: Dict[str, Any] = {"video": None, "audio": [], "subtitles": []}
    for s in data.get("streams", []):
        ctype = s.get("codec_type")
        tags = s.get("tags", {}) or {}
        disp = s.get("disposition", {}) or {}
        if ctype == "video" and info["video"] is None:
            info["video"] = {
                "codec": s.get("codec_name"),
                "width": s.get("width"),
                "height": s.get("height"),
            }
        elif ctype == "audio":
            info["audio"].append({
                "index": len(info["audio"]),
                "stream_index": s.get("index"),
                "language": tags.get("language", "und"),
                "label": tags.get("title") or lang_name(tags.get("language")),
                "codec": s.get("codec_name"),
                "channels": s.get("channels"),
                "default": bool(disp.get("default")),
            })
        elif ctype == "subtitle":
            info["subtitles"].append({
                "index": len(info["subtitles"]),
                "stream_index": s.get("index"),
                "language": tags.get("language", "und"),
                "label": tags.get("title") or lang_name(tags.get("language")),
                "codec": s.get("codec_name"),
                "forced": bool(disp.get("forced")),
                "text": s.get("codec_name") in TEXT_SUBTITLE_CODECS,
            })
    return info


def encode_audio(input_path: Path, output_path: Path, stream_index: int) -> Path:
    """Encode one source audio stream to an AAC MP4 for CMAF packaging."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(input_path),
        "-map", f"0:{stream_index}", "-vn",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        "-movflags", "+faststart", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"audio encode failed: {result.stderr}")
    return output_path


def extract_subtitle_to_vtt(input_path: Path, output_path: Path, stream_index: int) -> bool:
    """Convert one text subtitle stream to a sidecar WebVTT file."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(input_path),
        "-map", f"0:{stream_index}", "-c:s", "webvtt", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def _run_ffmpeg_progress(cmd: List[str], total: float, on_progress: ProgressCb | None) -> None:
    """Run ffmpeg, streaming -progress (out_time_us) into on_progress (0-100).

    stderr goes to a temp file so a full stderr pipe can't deadlock the reader.
    """
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
                on_progress(min(99, int((out_us / 1_000_000) / total * 100)))
        proc.wait()
        if proc.returncode != 0:
            err_file.seek(0)
            raise RuntimeError(f"ffmpeg failed: {err_file.read()}")


def build_rendition_command(
    input_path: Path,
    output_path: Path,
    profile: EncodingProfile,
    include_audio: bool,
) -> List[str]:
    """ffmpeg command to encode ONE rendition to an MP4 (with per-rendition progress).

    Uses NVENC + CUDA decode when USE_NVENC is set (GPU), else libx264 veryfast (CPU).
    """
    settings = get_settings()
    cmd: List[str] = [
        "ffmpeg", "-y", "-progress", "pipe:1", "-nostats", "-loglevel", "error",
    ]
    if settings.use_nvenc:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-threads", str(settings.ffmpeg_threads), "-i", str(input_path)]

    # format=yuv420p forces 4:2:0 so every browser/device can decode it.
    cmd += ["-vf", f"scale={profile.width}:{profile.height},format=yuv420p"]

    if settings.use_nvenc:
        cmd += [
            "-c:v", "h264_nvenc", "-preset", settings.nvenc_preset,
            "-b:v", profile.video_bitrate, "-maxrate", profile.maxrate,
            "-bufsize", profile.bufsize,
        ]
    else:
        cmd += [
            "-c:v", "libx264", "-preset", settings.x264_preset,
            "-b:v", profile.video_bitrate, "-maxrate", profile.maxrate,
            "-bufsize", profile.bufsize, "-profile:v", profile.profile,
        ]

    # Align keyframes to segment boundaries so all renditions cut at the same points.
    cmd += ["-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_DURATION})", "-sc_threshold", "0"]

    if include_audio:
        cmd += ["-map", "0:v:0", "-map", "0:a:0",
                "-c:a", "aac", "-b:a", profile.audio_bitrate, "-ar", "48000"]
    else:
        cmd += ["-map", "0:v:0", "-an"]

    cmd += ["-movflags", "+faststart", str(output_path)]
    return cmd


def encode_rendition(
    input_path: Path,
    output_path: Path,
    profile: EncodingProfile,
    include_audio: bool,
    total_seconds: float,
    on_progress: ProgressCb | None = None,
) -> Path:
    """Encode a single rendition MP4, reporting 0-100 progress for THIS rendition."""
    cmd = build_rendition_command(input_path, output_path, profile, include_audio)
    _run_ffmpeg_progress(cmd, total_seconds, on_progress)
    return output_path


def _label_hls_audio(master_path: Path, audio_tracks: List[Dict[str, Any]]) -> None:
    """ffmpeg names HLS audio 'audio_N' with no language; rewrite to LANGUAGE/NAME."""
    import re

    lines = master_path.read_text(encoding="utf-8").splitlines()
    ai = 0
    out: List[str] = []
    for line in lines:
        if line.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in line and ai < len(audio_tracks):
            t = audio_tracks[ai]
            line = re.sub(r'NAME="[^"]*"', f'NAME="{t["label"]}"', line)
            if "LANGUAGE=" not in line:
                line = line.replace("TYPE=AUDIO,", f'TYPE=AUDIO,LANGUAGE="{t["language"]}",', 1)
            ai += 1
        out.append(line)
    master_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def package_cmaf(
    video_paths: List[Path],
    audio_tracks: List[Dict[str, Any]],
    work_dir: Path,
) -> Dict[str, Path]:
    """Stream-copy the video renditions + per-language audio MP4s into ONE CMAF
    set: master.m3u8 + manifest.mpd. No re-encode (``-c copy``), so it's fast.

    ``audio_tracks`` is a list of {"path", "language", "label"} — each becomes a
    selectable audio rendition / DASH adaptation set.
    """
    cmd: List[str] = ["ffmpeg", "-y", "-loglevel", "error"]
    for p in video_paths:
        cmd += ["-i", str(p)]
    for a in audio_tracks:
        cmd += ["-i", str(a["path"])]

    n_v = len(video_paths)
    for i in range(n_v):
        cmd += ["-map", f"{i}:v:0"]
    for j in range(len(audio_tracks)):
        cmd += ["-map", f"{n_v + j}:a:0"]

    cmd += ["-c:v", "copy", "-c:a", "copy"]
    for j, a in enumerate(audio_tracks):
        cmd += [f"-metadata:s:a:{j}", f"language={a['language']}"]

    # All video in adaptation set 0; each audio in its own set (per language).
    video_streams = ",".join(str(i) for i in range(n_v))
    sets = [f"id=0,streams={video_streams}"]
    for j in range(len(audio_tracks)):
        sets.append(f"id={j + 1},streams={n_v + j}")

    cmd += [
        "-f", "dash", "-seg_duration", str(SEGMENT_DURATION),
        "-use_template", "1", "-use_timeline", "1",
        "-adaptation_sets", " ".join(sets), "-hls_playlist", "1",
        str(work_dir / DASH_MANIFEST),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"packaging failed: {result.stderr}")

    hls_master = work_dir / HLS_MASTER
    dash_manifest = work_dir / DASH_MANIFEST
    if not hls_master.exists() or not dash_manifest.exists():
        raise RuntimeError(
            f"packaging did not produce manifests (hls={hls_master.exists()}, "
            f"dash={dash_manifest.exists()})"
        )
    if audio_tracks:
        _label_hls_audio(hls_master, audio_tracks)
    return {"hls": hls_master, "dash": dash_manifest}
