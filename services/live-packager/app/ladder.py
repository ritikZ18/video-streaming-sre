"""Live ABR ladder + ffmpeg command construction.

Unlike the VOD worker (which encodes each rung to a file in a single pass and
then packages), a live channel runs ONE long-lived ffmpeg that continuously
writes a rolling HLS window. We keep the ladder small (≤3 rungs) so a single
GTX 1650 — or the CPU fallback — stays above realtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class Rung:
    height: int
    v_bitrate: str
    v_maxrate: str
    v_bufsize: str
    a_bitrate: str


# Full menu, high → low. `select_rungs` trims to the requested ceiling and caps
# the count so we never ask the encoder for more realtime streams than it can do.
_MENU: list[Rung] = [
    Rung(1080, "5000k", "5350k", "7500k", "192k"),
    Rung(720, "2800k", "3000k", "4200k", "128k"),
    Rung(480, "1200k", "1300k", "1800k", "128k"),
    Rung(360, "800k", "856k", "1200k", "96k"),
]

_MAX_RUNGS = 3


def select_rungs(max_height: int, hard_cap: int) -> list[Rung]:
    """Rungs at or below the requested ceiling (and the server hard cap), newest
    kept to at most 3. Always returns at least the lowest rung."""
    ceiling = min(max_height or hard_cap, hard_cap)
    usable = [r for r in _MENU if r.height <= ceiling]
    if not usable:
        usable = [_MENU[-1]]
    return usable[:_MAX_RUNGS]


def _video_codec_args(cfg: Settings) -> list[str]:
    if cfg.use_nvenc:
        # Low-latency NVENC: no B-frames, constrained VBR capped by -maxrate.
        return ["-c:v", "h264_nvenc", "-preset", cfg.nvenc_preset, "-tune", "ll", "-bf", "0"]
    return [
        "-c:v", "libx264",
        "-preset", cfg.x264_preset,
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
    ]


def _keyframe_args(cfg: Settings) -> list[str]:
    # Force a keyframe every segment boundary so every rung is segment-aligned and
    # switchable — independent of the (unknown, live) source frame rate.
    return [
        "-force_key_frames", f"expr:gte(t,n_forced*{cfg.hls_time})",
        "-sc_threshold", "0",
    ]


def _hls_output_args(
    out_dir: str, cfg: Settings, var_stream_map: str | None, record: bool = False
) -> list[str]:
    if record:
        # Recording: keep EVERY segment (full DVR) so the finished stream is a
        # complete VOD. ffmpeg writes #EXT-X-ENDLIST on graceful stop, so the same
        # segments become a valid on-demand ladder with no re-encode.
        list_size = "0"
        hls_flags = "independent_segments+program_date_time"
    else:
        # Live: roll the window (delete_segments) to stay low-latency + bounded.
        list_size = str(cfg.hls_list_size)
        hls_flags = "independent_segments+delete_segments+program_date_time"
    args = [
        "-f", "hls",
        "-hls_time", str(cfg.hls_time),
        "-hls_list_size", list_size,
        # PROGRAM-DATE-TIME lets the player show a wall-clock live edge.
        "-hls_flags", hls_flags,
        "-hls_segment_type", "mpegts",
    ]
    if var_stream_map:
        args += [
            "-master_pl_name", "master.m3u8",
            "-hls_segment_filename", f"{out_dir}/v%v_%d.ts",
            "-var_stream_map", var_stream_map,
            f"{out_dir}/stream_%v.m3u8",
        ]
    else:
        # Single rendition → the variant playlist IS the master.
        args += [
            "-hls_segment_filename", f"{out_dir}/seg_%d.ts",
            f"{out_dir}/master.m3u8",
        ]
    return args


_BASE = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-progress", "pipe:1", "-nostats"]


def build_command(
    input_args: list[str],
    out_dir: str,
    rungs: list[Rung],
    audio_only: bool,
    cfg: Settings,
    record: bool = False,
) -> list[str]:
    """Full ffmpeg argv for a live channel. `input_args` is everything up to and
    including `-i <source>` (it carries -re / -stream_loop / reconnect flags).
    `record=True` keeps every segment so the stream doubles as a VOD recording."""
    if audio_only:
        return [
            *_BASE, *input_args,
            "-vn", "-c:a", "aac", "-ac", "2", "-b:a", "160k",
            *_hls_output_args(out_dir, cfg, var_stream_map=None, record=record),
        ]

    n = len(rungs)
    if n == 1:
        r = rungs[0]
        return [
            *_BASE, *input_args,
            "-vf", f"scale=-2:{r.height}",
            *_video_codec_args(cfg),
            "-b:v", r.v_bitrate, "-maxrate", r.v_maxrate, "-bufsize", r.v_bufsize,
            *_keyframe_args(cfg),
            "-map", "0:a:0?", "-c:a", "aac", "-ac", "2", "-b:a", r.a_bitrate,
            *_hls_output_args(out_dir, cfg, var_stream_map=None, record=record),
        ]

    # Multi-rung: split the decoded video once, scale each branch, encode all.
    splits = "".join(f"[v{i}]" for i in range(n))
    filt = f"[0:v]split={n}{splits}"
    for i, r in enumerate(rungs):
        filt += f";[v{i}]scale=-2:{r.height}[v{i}o]"

    cmd = [*_BASE, *input_args, "-filter_complex", filt]
    # Map every video branch, then the source audio once per branch (var_stream_map
    # pairs v:i with a:i).
    for i in range(n):
        cmd += ["-map", f"[v{i}o]"]
    for _ in range(n):
        cmd += ["-map", "0:a:0?"]

    cmd += _video_codec_args(cfg)
    for i, r in enumerate(rungs):
        cmd += [f"-b:v:{i}", r.v_bitrate, f"-maxrate:v:{i}", r.v_maxrate, f"-bufsize:v:{i}", r.v_bufsize]
    cmd += _keyframe_args(cfg)

    cmd += ["-c:a", "aac", "-ac", "2"]
    for i, r in enumerate(rungs):
        cmd += [f"-b:a:{i}", r.a_bitrate]

    var_stream_map = " ".join(f"v:{i},a:{i}" for i in range(n))
    cmd += _hls_output_args(out_dir, cfg, var_stream_map=var_stream_map, record=record)
    return cmd


def build_test_command(out_dir: str, cfg: Settings) -> list[str]:
    """A self-contained test channel (colour bars + a tone) — verifies the whole
    packager→origin→player path with no upload and no encoder."""
    return [
        *_BASE,
        "-re", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
        "-re", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
        "-b:v", "2500k", "-maxrate", "2675k", "-bufsize", "3750k",
        *_keyframe_args(cfg),
        "-c:a", "aac", "-ac", "2", "-b:a", "128k",
        *_hls_output_args(out_dir, cfg, var_stream_map=None),
    ]
