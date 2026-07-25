from __future__ import annotations

import json
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from app.config import get_settings
from app.profiles import PROFILES, EncodingProfile, ladder_for

logger = structlog.get_logger()


class JobCancelled(Exception):
    """Raised when a cancel was requested mid-transcode so the pipeline aborts.

    Deliberately NOT a RuntimeError, so the NVENC->CPU fallback in
    encode_rendition does not swallow it — cancellation must propagate.
    """

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
CancelCb = Callable[[], bool]


def has_audio_stream(input_path: Path) -> bool:
    """Return True if the input has at least one audio stream (via ffprobe)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(input_path)],
        capture_output=True, text=True, check=False,
    )
    return bool(result.stdout.strip())


def probe_duration(input_path: Path) -> float | None:
    """Return the media duration in seconds (via ffprobe), or None."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(input_path)],
        capture_output=True, text=True, check=False,
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
        capture_output=True, text=True, check=False,
    )
    return result.returncode == 0 and output_path.exists()


def probe_media(input_path: Path) -> dict[str, Any]:
    """Full ffprobe (the 'VLC' metadata): video + audio tracks + subtitle tracks."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(input_path)],
        capture_output=True, text=True, check=False,
    )
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        data = {}

    info: dict[str, Any] = {"video": None, "audio": [], "subtitles": []}
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
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"audio encode failed: {result.stderr}")
    return output_path


def extract_subtitle_to_vtt(input_path: Path, output_path: Path, stream_index: int) -> bool:
    """Convert one text subtitle stream to a sidecar WebVTT file."""
    cmd = [
        "ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(input_path),
        "-map", f"0:{stream_index}", "-c:s", "webvtt", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0


def extract_subtitles_batch(
    input_path: Path,
    specs: list[dict[str, Any]],
    subs_dir: Path,
) -> list[tuple[dict[str, Any], Path]]:
    """Extract many text subtitle streams to WebVTT in ONE demux pass.

    specs: subtitle dicts (from probe_media) with stream_index/language/index.
    A source with a dozen subtitle tracks otherwise costs a dozen full demuxes
    of a multi-hundred-MB file; here we demux once and write every VTT output.
    Returns (spec, path) for each track that produced a non-empty file (checked
    by existence so a single bad stream doesn't discard the rest)."""
    text_specs = [s for s in specs if s.get("text")]
    if not text_specs:
        return []
    subs_dir.mkdir(exist_ok=True)
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(input_path)]
    planned: list[tuple[dict[str, Any], Path]] = []
    for s in text_specs:
        vtt = subs_dir / f"{s['language']}_{s['index']}.vtt"
        cmd += ["-map", f"0:{s['stream_index']}", "-c:s", "webvtt", str(vtt)]
        planned.append((s, vtt))
    subprocess.run(cmd, capture_output=True, text=True, check=False)
    good = [(s, vtt) for s, vtt in planned if vtt.exists() and vtt.stat().st_size > 0]
    if not good:
        # Single-pass produced nothing (one bad stream can abort ffmpeg); fall
        # back to per-track extraction so healthy tracks still come through.
        for s, vtt in planned:
            if extract_subtitle_to_vtt(input_path, vtt, s["stream_index"]):
                good.append((s, vtt))
    return good


def _run_ffmpeg_progress(
    cmd: list[str],
    total: float,
    on_progress: ProgressCb | None,
    should_cancel: CancelCb | None = None,
) -> None:
    """Run ffmpeg, streaming -progress (out_time_us) into on_progress (0-100).

    stderr goes to a temp file so a full stderr pipe can't deadlock the reader.
    If should_cancel() returns True mid-encode, the ffmpeg process is killed and
    JobCancelled is raised (checked on each progress line; the callback itself is
    throttled by the caller so this stays cheap).
    """
    with tempfile.TemporaryFile(mode="w+") as err_file:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err_file, text=True)
        if proc.stdout is not None:
            for raw in proc.stdout:
                if should_cancel and should_cancel():
                    proc.kill()
                    proc.wait()
                    raise JobCancelled()
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
    use_nvenc: bool | None = None,
) -> list[str]:
    """ffmpeg command to encode ONE rendition to an MP4 (with per-rendition progress).

    Uses NVENC + CUDA decode when use_nvenc is set (defaults to the USE_NVENC
    setting), else libx264 veryfast (CPU). Pass use_nvenc=False to force the CPU
    path — used as the automatic fallback when the GPU encoder is unavailable.
    """
    settings = get_settings()
    if use_nvenc is None:
        use_nvenc = settings.use_nvenc
    cmd: list[str] = [
        "ffmpeg", "-y", "-progress", "pipe:1", "-nostats", "-loglevel", "error",
    ]
    if use_nvenc:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-threads", str(settings.ffmpeg_threads), "-i", str(input_path)]

    # format=yuv420p forces 4:2:0 so every browser/device can decode it
    # (also downconverts 10-bit HDR/HEVC sources to 8-bit SDR).
    cmd += ["-vf", f"scale={profile.width}:{profile.height},format=yuv420p"]

    if use_nvenc:
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
    should_cancel: CancelCb | None = None,
) -> Path:
    """Encode a single rendition MP4, reporting 0-100 progress for THIS rendition.

    When NVENC is enabled but the GPU encoder is unavailable at runtime (missing
    driver libs, exhausted encode sessions, unsupported input), the first attempt
    fails; we transparently retry on CPU (libx264) so a job never hard-sticks.
    A JobCancelled from should_cancel() is re-raised (not treated as an NVENC
    failure) so cancellation aborts instead of silently retrying on CPU.
    """
    settings = get_settings()
    if settings.use_nvenc:
        gpu_cmd = build_rendition_command(
            input_path, output_path, profile, include_audio, use_nvenc=True
        )
        try:
            _run_ffmpeg_progress(gpu_cmd, total_seconds, on_progress, should_cancel)
            return output_path
        except RuntimeError as exc:
            logger.warning(
                "nvenc_failed_falling_back_to_cpu",
                rendition=profile.name,
                error=str(exc)[:300],
            )

    cpu_cmd = build_rendition_command(
        input_path, output_path, profile, include_audio, use_nvenc=False
    )
    _run_ffmpeg_progress(cpu_cmd, total_seconds, on_progress, should_cancel)
    return output_path


def build_ladder_command(
    input_path: Path,
    outputs: list[tuple[EncodingProfile, Path]],
    use_nvenc: bool,
) -> list[str]:
    """Single-pass command: decode the source ONCE and emit every rendition.

    GPU path (use_nvenc): NVDEC decode -> keep frames on the GPU
    (-hwaccel_output_format cuda) -> split -> scale_cuda per rendition (resize +
    10-bit->8-bit on the GPU) -> one h264_nvenc encoder per rendition. No CPU
    scale, and the expensive decode happens once instead of once-per-rendition.

    CPU fallback: decode once -> split -> libswscale scale per rendition -> libx264.
    """
    settings = get_settings()
    n = len(outputs)
    cmd: list[str] = ["ffmpeg", "-y", "-progress", "pipe:1", "-nostats", "-loglevel", "error"]
    if use_nvenc:
        cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    cmd += ["-i", str(input_path)]

    split = f"[0:v]split={n}" + "".join(f"[s{i}]" for i in range(n))
    chains: list[str] = []
    for i, (prof, _) in enumerate(outputs):
        if use_nvenc:
            chains.append(f"[s{i}]scale_cuda={prof.width}:{prof.height}:format=yuv420p[v{i}]")
        else:
            chains.append(f"[s{i}]scale={prof.width}:{prof.height},format=yuv420p[v{i}]")
    cmd += ["-filter_complex", ";".join([split] + chains)]

    for i, (prof, outp) in enumerate(outputs):
        cmd += ["-map", f"[v{i}]"]
        if use_nvenc:
            cmd += ["-c:v", "h264_nvenc", "-preset", settings.nvenc_preset]
        else:
            cmd += ["-c:v", "libx264", "-preset", settings.x264_preset, "-profile:v", prof.profile]
        cmd += [
            "-b:v", prof.video_bitrate, "-maxrate", prof.maxrate, "-bufsize", prof.bufsize,
            "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_DURATION})", "-sc_threshold", "0",
            "-an", "-movflags", "+faststart", str(outp),
        ]
    return cmd


def encode_ladder(
    input_path: Path,
    renditions_dir: Path,
    total_seconds: float,
    source_height: int = 0,
    on_progress: ProgressCb | None = None,
    should_cancel: CancelCb | None = None,
) -> list[Path]:
    """Encode the rendition ladder in a single decode pass; return output paths.
    The ladder is chosen by ladder_for(source_height) so a 4K source produces
    up to 2160p while smaller sources are never upscaled. Tries the GPU ladder
    first (when NVENC is on) and falls back to a single-pass CPU ladder."""
    settings = get_settings()
    outputs = [(p, renditions_dir / f"v_{p.name}.mp4") for p in ladder_for(source_height)]
    if settings.use_nvenc:
        # NVENC occasionally fails to initialise on a cold worker / transient
        # driver state ("GPU sometimes doesn't start"), so retry the GPU path
        # once (after a short settle) before giving up on it.
        for attempt in range(2):
            try:
                _run_ffmpeg_progress(
                    build_ladder_command(input_path, outputs, use_nvenc=True),
                    total_seconds, on_progress, should_cancel,
                )
                return [outp for _, outp in outputs]
            except RuntimeError as exc:
                logger.warning("nvenc_ladder_failed", attempt=attempt, error=str(exc)[:300])
                if attempt == 0:
                    time.sleep(2.0)

    logger.warning("ladder_using_cpu_fallback")
    _run_ffmpeg_progress(
        build_ladder_command(input_path, outputs, use_nvenc=False),
        total_seconds, on_progress, should_cancel,
    )
    return [outp for _, outp in outputs]


def _label_hls_audio(master_path: Path, audio_tracks: list[dict[str, Any]]) -> None:
    """ffmpeg names HLS audio 'audio_N' with no language; rewrite to LANGUAGE/NAME."""
    import re

    lines = master_path.read_text(encoding="utf-8").splitlines()
    ai = 0
    out: list[str] = []
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
    video_paths: list[Path],
    audio_tracks: list[dict[str, Any]],
    work_dir: Path,
) -> dict[str, Path]:
    """Stream-copy the video renditions + per-language audio MP4s into ONE CMAF
    set: master.m3u8 + manifest.mpd. No re-encode (``-c copy``), so it's fast.

    ``audio_tracks`` is a list of {"path", "language", "label"} — each becomes a
    selectable audio rendition / DASH adaptation set.
    """
    cmd: list[str] = ["ffmpeg", "-y", "-loglevel", "error"]
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

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
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
