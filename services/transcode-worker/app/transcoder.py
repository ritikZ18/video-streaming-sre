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
                # Color signalling — used to detect HDR (PQ/HLG) sources so they
                # get an HDR-preserving HEVC tier + a tonemapped H.264 fallback.
                "color_transfer": s.get("color_transfer"),
                "pix_fmt": s.get("pix_fmt"),
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
    """Encode one source audio stream to a STEREO AAC MP4 for CMAF packaging.

    ``-ac 2`` downmixes multichannel sources (e.g. Dolby 5.1 = 6 channels) to
    stereo. Browsers fail to append 6-channel AAC in a demuxed HLS SourceBuffer,
    so a 5.1 title would refuse to play in any browser; stereo plays everywhere
    (and web output is stereo anyway)."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(input_path),
        "-map", f"0:{stream_index}", "-vn",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"audio encode failed: {result.stderr}")
    return output_path


def encode_external_audio(
    input_path: Path, output_path: Path, duration_seconds: float = 0.0
) -> Path:
    """Encode an ADMIN-ATTACHED external audio file to stereo AAC for a silent
    title. When the video duration is known, pad-with-silence (``apad``) and cap
    (``-t``) so the track lines up exactly with the video — a shorter track gets
    trailing silence, a longer one is trimmed — keeping the CMAF segments clean.
    With an unknown duration it takes the audio as-is."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(input_path), "-vn"]
    if duration_seconds and duration_seconds > 0:
        cmd += ["-af", "apad", "-t", f"{duration_seconds:.3f}"]
    cmd += [
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"external audio encode failed: {result.stderr}")
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


# --- Encode quality ---------------------------------------------------------
# Fixed bitrate spends the same bits on a static shot and a busy action scene;
# constant-quality (CQ) VBR targets a visual QUALITY instead, so complex frames
# get more bits automatically. A per-profile -maxrate cap keeps peak bitrate
# streamable. Flag sets validated on this GTX 1650: H.264 8-bit takes the full
# NVENC tuning; HEVC Main10 is kept conservative (spatial-aq / rc-lookahead can
# report "No capable devices" for 10-bit on this Turing card).
NVENC_CQ_H264 = "20"
NVENC_CQ_HEVC = "23"  # HEVC is more efficient — a higher CQ ~ H.264's quality
_NVENC_CORE = ["-rc", "vbr", "-b:v", "0", "-preset", "p7", "-tune", "hq"]
_NVENC_H264_EXTRA = [
    "-spatial-aq", "1", "-temporal-aq", "1", "-aq-strength", "8",
    "-rc-lookahead", "20", "-b_ref_mode", "middle", "-multipass", "fullres",
]
_NVENC_HEVC_EXTRA = ["-multipass", "fullres"]

# HDR (BT.2020 / PQ) signalling kept on the HEVC tier so the picture stays HDR.
_HDR_TAGS = ["-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc"]
# HDR->SDR tone-map (Hable), applied ONCE before the split, then scaled per rung.
_TONEMAP = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv"
)

# Source color transfers that mean HDR (PQ / HLG).
_HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


def is_hdr(media: dict[str, Any]) -> bool:
    """True if the source signals HDR (PQ/HLG). HDR gets an HDR-preserving HEVC
    tier plus a tonemapped H.264 fallback; SDR gets a single H.264 ladder."""
    ct = ((media.get("video") or {}).get("color_transfer") or "").lower()
    return ct in _HDR_TRANSFERS


def can_nvdec_decode(media: dict[str, Any]) -> bool:
    """True if this GPU's NVDEC can decode the source, so the full-GPU path is
    worth trying. AV1 has no NVDEC on Turing (GTX 1650), and NVDEC H.264 is 8-bit
    only — for those we skip straight to the CPU-decode + NVENC hybrid instead of
    burning ~a minute on two doomed full-GPU attempts per job."""
    v = media.get("video") or {}
    codec = (v.get("codec") or "").lower()
    pix = (v.get("pix_fmt") or "").lower()
    if codec == "av1":
        return False
    if codec == "h264" and "10" in pix:  # High 10 / 10-bit H.264
        return False
    return True


def build_ladder_command(
    input_path: Path,
    outputs: list[tuple[EncodingProfile, Path]],
    *,
    codec: str,          # "h264" | "hevc"
    use_nvenc: bool,     # NVENC vs libx264/libx265
    gpu_decode: bool,    # NVDEC + scale_cuda (only valid for SDR sources)
    mode: str,           # "sdr" | "hdr_preserve" | "hdr_tonemap"
) -> list[str]:
    """One single-pass ladder command for ONE codec: decode the source ONCE,
    split, scale per rung, encode each rung with CQ-VBR (+ a -maxrate cap).

    mode:
      - ``sdr``          -> 8-bit yuv420p, bt709.
      - ``hdr_preserve`` -> 10-bit p010, BT.2020/PQ kept (the HEVC tier).
      - ``hdr_tonemap``  -> HDR->SDR (Hable) once, then 8-bit (the H.264 fallback).
    ``gpu_decode`` uses NVDEC + ``scale_cuda`` (only for SDR sources the GPU can
    decode); otherwise CPU decode + libswscale lanczos. GPU lanczos isn't in this
    ffmpeg build, so lanczos is applied on the CPU-scale path only.
    """
    settings = get_settings()
    n = len(outputs)
    hw_decode = use_nvenc and gpu_decode and mode == "sdr"
    pix = "p010le" if mode == "hdr_preserve" else "yuv420p"

    cmd: list[str] = ["ffmpeg", "-y", "-progress", "pipe:1", "-nostats", "-loglevel", "error"]
    if hw_decode:
        cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    cmd += ["-i", str(input_path)]

    # (optional one-time HDR->SDR tonemap) -> split -> per-rung scale
    head = f"[0:v]{_TONEMAP}[tm];[tm]" if mode == "hdr_tonemap" else "[0:v]"
    split = f"{head}split={n}" + "".join(f"[s{i}]" for i in range(n))
    # Aspect-preserving downscale (fit inside the rung box, even dimensions, never
    # upscale) so non-16:9 sources keep their shape and full width instead of being
    # stretched into the profile's exact WxH.
    fit = "force_original_aspect_ratio=decrease:force_divisible_by=2"
    chains: list[str] = []
    for i, (prof, _) in enumerate(outputs):
        if hw_decode:
            chains.append(f"[s{i}]scale_cuda={prof.width}:{prof.height}:{fit}:format={pix}[v{i}]")
        else:
            chains.append(f"[s{i}]scale={prof.width}:{prof.height}:{fit}:flags=lanczos,format={pix}[v{i}]")
    cmd += ["-filter_complex", ";".join([split] + chains)]

    for i, (prof, outp) in enumerate(outputs):
        cmd += ["-map", f"[v{i}]"]
        if use_nvenc and codec == "hevc":
            cmd += ["-c:v", "hevc_nvenc", "-tag:v", "hvc1"]
            if mode == "hdr_preserve":
                cmd += ["-profile:v", "main10"]
            cmd += ["-cq", NVENC_CQ_HEVC, *_NVENC_CORE, *_NVENC_HEVC_EXTRA]
        elif use_nvenc:  # h264_nvenc
            cmd += ["-c:v", "h264_nvenc", "-cq", NVENC_CQ_H264, *_NVENC_CORE, *_NVENC_H264_EXTRA]
        elif codec == "hevc":
            cmd += ["-c:v", "libx265", "-preset", settings.x264_preset, "-crf", "24", "-tag:v", "hvc1"]
        else:  # libx264 CPU last resort
            cmd += ["-c:v", "libx264", "-preset", settings.x264_preset, "-crf", "20", "-profile:v", prof.profile]
        # Cap the peak so CQ output stays streamable + align keyframes to segments.
        cmd += [
            "-maxrate", prof.maxrate, "-bufsize", prof.bufsize,
            "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_DURATION})", "-sc_threshold", "0",
        ]
        if mode == "hdr_preserve":
            cmd += _HDR_TAGS
        cmd += ["-an", "-movflags", "+faststart", str(outp)]
    return cmd


def _encode_one_ladder(
    input_path: Path,
    outputs: list[tuple[EncodingProfile, Path]],
    codec: str,
    mode: str,
    total_seconds: float,
    on_progress: ProgressCb | None,
    should_cancel: CancelCb | None,
    gpu_decodable: bool = True,
) -> list[Path]:
    """Encode ONE codec's ladder with the full-GPU -> hybrid -> CPU fallback.

    SDR with an NVDEC-decodable source tries full-GPU (NVDEC+NVENC, retried once
    for cold NVENC), then hybrid (CPU decode + NVENC), then CPU. Sources this GPU
    can't NVDEC-decode (AV1, 10-bit H.264) or any HDR mode skip full-GPU and start
    at the hybrid, so we don't burn time on attempts that always fail.
    """
    settings = get_settings()

    def run(use_nvenc: bool, gpu_decode: bool) -> None:
        _run_ffmpeg_progress(
            build_ladder_command(
                input_path, outputs, codec=codec, use_nvenc=use_nvenc,
                gpu_decode=gpu_decode, mode=mode,
            ),
            total_seconds, on_progress, should_cancel,
        )

    if settings.use_nvenc:
        if mode == "sdr" and gpu_decodable:
            for attempt in range(2):  # full GPU, retry once for cold-start NVENC
                try:
                    run(use_nvenc=True, gpu_decode=True)
                    return [o for _, o in outputs]
                except RuntimeError as exc:
                    logger.warning("gpu_ladder_failed", codec=codec, attempt=attempt, error=str(exc)[:200])
                    if attempt == 0:
                        time.sleep(2.0)
        try:  # hybrid: CPU decode + NVENC encode
            logger.warning("hybrid_cpu_decode_gpu_encode", codec=codec, mode=mode)
            run(use_nvenc=True, gpu_decode=False)
            return [o for _, o in outputs]
        except RuntimeError as exc:
            logger.warning("hybrid_ladder_failed", codec=codec, error=str(exc)[:200])

    logger.warning("ladder_using_cpu_fallback", codec=codec, mode=mode)
    run(use_nvenc=False, gpu_decode=False)
    return [o for _, o in outputs]


def encode_ladder(
    input_path: Path,
    renditions_dir: Path,
    total_seconds: float,
    source_height: int = 0,
    hdr: bool = False,
    gpu_decodable: bool = True,
    on_progress: ProgressCb | None = None,
    should_cancel: CancelCb | None = None,
) -> list[tuple[str, list[Path]]]:
    """Encode the rendition ladder(s); return ``[(codec, [rung paths]), ...]``.

    - **SDR source** -> one H.264 ladder (universal), quality-upgraded.
    - **HDR source** -> an HEVC-Main10 ladder that KEEPS the HDR **plus** a
      tonemapped H.264 SDR ladder. Both are packaged into one master so HDR-capable
      players use HEVC and everything else falls back to H.264.

    The ladder is chosen by ladder_for(source_height) so a 4K source produces up
    to 2160p and smaller sources are never upscaled.
    """
    profiles = ladder_for(source_height)

    def outs(codec: str) -> list[tuple[EncodingProfile, Path]]:
        return [(p, renditions_dir / f"v_{codec}_{p.name}.mp4") for p in profiles]

    if not hdr:
        paths = _encode_one_ladder(
            input_path, outs("h264"), "h264", "sdr",
            total_seconds, on_progress, should_cancel,
            gpu_decodable=gpu_decodable,
        )
        return [("h264", paths)]

    # HDR: split the progress budget across the two ladders so the bar climbs 0->100.
    def scaled(lo: int, hi: int) -> ProgressCb | None:
        if on_progress is None:
            return None
        return lambda p: on_progress(int(lo + (hi - lo) * p / 100))

    # Encode + list H.264-SDR FIRST (universal, always plays) then the
    # HDR-preserving HEVC tier. H.264 first makes it the default variant, so a
    # browser that can't decode HEVC never gets stuck on the HEVC ladder.
    h264_paths = _encode_one_ladder(
        input_path, outs("h264"), "h264", "hdr_tonemap",
        total_seconds, scaled(0, 50), should_cancel,
    )
    hevc_paths = _encode_one_ladder(
        input_path, outs("hevc"), "hevc", "hdr_preserve",
        total_seconds, scaled(50, 100), should_cancel,
    )
    return [("h264", h264_paths), ("hevc", hevc_paths)]


# Precise HEVC Main10 RFC 6381 codec string (level 5.1 covers up to 1440p60). The
# profile digit (2 = Main10) is what browsers gate on when deciding decode support.
HEVC_CODEC = "hvc1.2.4.L153.B0"


def _split_masters(master_path: Path) -> Path | None:
    """Split ffmpeg's combined dual-codec master into two single-codec masters:

    - ``master.m3u8``      — H.264 variants only. The universal default the player
      loads first; it plays in every browser.
    - ``master_hevc.m3u8`` — HEVC variants only, with a precise Main10 codec string.
      The HDR tier; the player switches to it only when the browser can actually
      decode HEVC (checked via mediaCapabilities). Written only if HEVC variants
      exist (SDR videos get no HEVC master).

    Serving one MIXED master breaks Chrome (it claims bare-hvc1 support, then fails
    to decode 10-bit HDR HEVC and never falls back) — hence two separate masters.
    Returns the HEVC master path, or None for SDR.
    """
    header: list[str] = []
    h264: list[str] = []
    hevc: list[str] = []
    lines = master_path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("#EXT-X-STREAM-INF"):
            uri = lines[i + 1] if i + 1 < len(lines) else ""
            if "hvc1" in ln:
                ln = ln.replace('CODECS="hvc1,', f'CODECS="{HEVC_CODEC},')
                ln = ln.replace('CODECS="hvc1"', f'CODECS="{HEVC_CODEC}"')
                hevc += [ln, uri]
            else:
                h264 += [ln, uri]
            i += 2
        else:
            if ln.strip():  # keep header lines (#EXTM3U, VERSION, audio EXT-X-MEDIA)
                header.append(ln)
            i += 1
    if not hevc:
        return None  # SDR — master.m3u8 already H.264-only
    master_path.write_text("\n".join(header + h264) + "\n", encoding="utf-8")
    hevc_path = master_path.with_name("master_hevc.m3u8")
    hevc_path.write_text("\n".join(header + hevc) + "\n", encoding="utf-8")
    return hevc_path


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
    video_sets: list[tuple[str, list[Path]]],
    audio_tracks: list[dict[str, Any]],
    work_dir: Path,
) -> dict[str, Path]:
    """Stream-copy the video renditions (one or two codecs) + per-language audio
    into ONE CMAF set: master.m3u8 + manifest.mpd. No re-encode (``-c copy``).

    ``video_sets`` is ``[(codec, [rung mp4s]), ...]`` — HDR has two sets (HEVC +
    H.264). Each codec gets its OWN DASH adaptation set (a set must be single-codec
    /switchable); in the HLS master they show as variants and the player picks the
    best codec it can decode (HEVC-HDR, else H.264-SDR).
    ``audio_tracks`` is a list of {"path", "language", "label"}.
    """
    # Flatten to (codec, path) in a stable order, tracking which stream indices
    # belong to each codec for the adaptation-set grouping.
    videos: list[tuple[str, Path]] = [(codec, p) for codec, paths in video_sets for p in paths]

    cmd: list[str] = ["ffmpeg", "-y", "-loglevel", "error"]
    for _, p in videos:
        cmd += ["-i", str(p)]
    for a in audio_tracks:
        cmd += ["-i", str(a["path"])]

    n_v = len(videos)
    for i in range(n_v):
        cmd += ["-map", f"{i}:v:0"]
    for j in range(len(audio_tracks)):
        cmd += ["-map", f"{n_v + j}:a:0"]

    cmd += ["-c:v", "copy", "-c:a", "copy"]
    for j, a in enumerate(audio_tracks):
        cmd += [f"-metadata:s:a:{j}", f"language={a['language']}"]

    # One video adaptation set PER codec, then one per audio language.
    groups: dict[str, list[int]] = {}
    order: list[str] = []
    for i, (codec, _) in enumerate(videos):
        if codec not in groups:
            groups[codec] = []
            order.append(codec)
        groups[codec].append(i)

    sets: list[str] = []
    sid = 0
    for codec in order:
        sets.append(f"id={sid},streams={','.join(str(i) for i in groups[codec])}")
        sid += 1
    for j in range(len(audio_tracks)):
        sets.append(f"id={sid},streams={n_v + j}")
        sid += 1

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
    # Split the combined master into an H.264 default + a separate HEVC (HDR)
    # master. hls_hevc is None for SDR videos (no HEVC variants).
    hls_hevc = _split_masters(hls_master)
    return {"hls": hls_master, "hls_hevc": hls_hevc, "dash": dash_manifest}
