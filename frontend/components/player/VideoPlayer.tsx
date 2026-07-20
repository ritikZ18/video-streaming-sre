"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Maximize,
  Minimize,
  Loader2,
  RotateCcw,
  Settings,
  Gauge,
} from "lucide-react";
import { sendBeacon, type BeaconEvent } from "../../lib/api";

type VideoPlayerProps = {
  src: string | null;
  poster?: string | null;
  title?: string | null;
  contentId?: string | null;
};

type Level = { index: number; height: number; bitrateKbps: number };

function fmt(t: number): string {
  if (!Number.isFinite(t) || t < 0) return "0:00";
  const s = Math.floor(t % 60);
  const m = Math.floor((t / 60) % 60);
  const h = Math.floor(t / 3600);
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  return `${h > 0 ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

export function VideoPlayer({ src, poster, title, contentId }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [buffered, setBuffered] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [menu, setMenu] = useState<null | "quality" | "speed">(null);

  const [levels, setLevels] = useState<Level[]>([]);
  const [currentLevel, setCurrentLevel] = useState(-1); // -1 = auto
  const [rate, setRate] = useState(1);

  const [showStats, setShowStats] = useState(false);
  const [bitrateKbps, setBitrateKbps] = useState(0);
  const [rebuffers, setRebuffers] = useState(0);
  const [startupMs, setStartupMs] = useState<number | null>(null);

  // Beacon / QoE bookkeeping.
  const sessionRef = useRef<string>("");
  const eventsRef = useRef<BeaconEvent[]>([]);
  const loadStartRef = useRef(0);
  const rebufferStartRef = useRef(0);
  const gotFirstFrameRef = useRef(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const pushEvent = useCallback((e: Omit<BeaconEvent, "timestamp">) => {
    eventsRef.current.push({ ...e, timestamp: new Date().toISOString() });
  }, []);

  const flush = useCallback(() => {
    if (!eventsRef.current.length) return;
    sendBeacon({
      session_id: sessionRef.current,
      content_id: contentId ?? undefined,
      player_version: "1.0.0",
      events: eventsRef.current.splice(0),
    });
  }, [contentId]);

  // ---- HLS attach ----
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;

    sessionRef.current =
      (typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `sess-${Math.floor(performance.now())}`);
    eventsRef.current = [];
    gotFirstFrameRef.current = false;
    loadStartRef.current = performance.now();
    setError(null);
    setStarted(false);
    setLevels([]);
    setCurrentLevel(-1);

    let hls: Hls | null = null;

    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src; // native HLS (Safari)
    } else if (Hls.isSupported()) {
      hls = new Hls({ enableWorker: true, lowLatencyMode: false, backBufferLength: 60 });
      hlsRef.current = hls;
      hls.loadSource(src);
      hls.attachMedia(video);

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setLevels(
          hls!.levels.map((l, i) => ({
            index: i,
            height: l.height,
            bitrateKbps: Math.round((l.bitrate || 0) / 1000),
          })),
        );
      });
      hls.on(Hls.Events.LEVEL_SWITCHED, (_e, data) => {
        const lvl = hls!.levels[data.level];
        if (lvl) {
          const kbps = Math.round((lvl.bitrate || 0) / 1000);
          setBitrateKbps(kbps);
          setCurrentLevel(hls!.autoLevelEnabled ? -1 : data.level);
          pushEvent({ event: "bitrate_switch", current_bitrate_kbps: kbps });
        }
      });
      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (data.fatal) {
          pushEvent({ event: "error", error_type: data.details });
          setError(`Playback error: ${data.details}`);
        }
      });
    } else {
      setError("HLS is not supported in this browser.");
    }

    return () => {
      flush();
      if (hls) hls.destroy();
      hlsRef.current = null;
    };
  }, [src, flush, pushEvent]);

  // ---- <video> events ----
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onTime = () => {
      setCurrent(video.currentTime);
      if (video.buffered.length) setBuffered(video.buffered.end(video.buffered.length - 1));
    };
    const onMeta = () => setDuration(video.duration || 0);
    const onWaiting = () => {
      setLoading(true);
      if (gotFirstFrameRef.current) rebufferStartRef.current = performance.now();
    };
    const onPlaying = () => {
      setLoading(false);
      setStarted(true);
      if (!gotFirstFrameRef.current) {
        gotFirstFrameRef.current = true;
        const ms = Math.round(performance.now() - loadStartRef.current);
        setStartupMs(ms);
        pushEvent({ event: "startup", startup_ms: ms });
      } else if (rebufferStartRef.current) {
        const ms = Math.round(performance.now() - rebufferStartRef.current);
        rebufferStartRef.current = 0;
        setRebuffers((r) => r + 1);
        pushEvent({ event: "rebuffer", rebuffer_ms: ms });
      }
    };
    const onVol = () => {
      setVolume(video.volume);
      setMuted(video.muted);
    };
    const onEnded = () => setPlaying(false);

    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("timeupdate", onTime);
    video.addEventListener("loadedmetadata", onMeta);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("playing", onPlaying);
    video.addEventListener("volumechange", onVol);
    video.addEventListener("ended", onEnded);
    return () => {
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("timeupdate", onTime);
      video.removeEventListener("loadedmetadata", onMeta);
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("playing", onPlaying);
      video.removeEventListener("volumechange", onVol);
      video.removeEventListener("ended", onEnded);
    };
  }, [pushEvent]);

  // ---- periodic beacon flush + heartbeat ----
  useEffect(() => {
    const id = setInterval(() => {
      if (playing) pushEvent({ event: "heartbeat", current_bitrate_kbps: bitrateKbps });
      flush();
    }, 15000);
    return () => {
      clearInterval(id);
      flush();
    };
  }, [playing, bitrateKbps, flush, pushEvent]);

  // ---- fullscreen state ----
  useEffect(() => {
    const onFs = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  }, []);

  const seek = useCallback((t: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = Math.max(0, Math.min(t, v.duration || t));
  }, []);

  const toggleMute = useCallback(() => {
    const v = videoRef.current;
    if (v) v.muted = !v.muted;
  }, []);

  const toggleFullscreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen();
  }, []);

  const setQuality = (index: number) => {
    const hls = hlsRef.current;
    if (hls) hls.currentLevel = index; // -1 = auto
    setCurrentLevel(index);
    setMenu(null);
  };

  const setSpeed = (r: number) => {
    const v = videoRef.current;
    if (v) v.playbackRate = r;
    setRate(r);
    setMenu(null);
  };

  // ---- keyboard shortcuts ----
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const v = videoRef.current;
      if (!v) return;
      switch (e.key.toLowerCase()) {
        case " ":
        case "k":
          e.preventDefault();
          togglePlay();
          break;
        case "arrowleft":
        case "j":
          seek(v.currentTime - 10);
          break;
        case "arrowright":
        case "l":
          seek(v.currentTime + 10);
          break;
        case "arrowup":
          v.volume = Math.min(1, v.volume + 0.1);
          break;
        case "arrowdown":
          v.volume = Math.max(0, v.volume - 0.1);
          break;
        case "f":
          toggleFullscreen();
          break;
        case "m":
          toggleMute();
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePlay, seek, toggleFullscreen, toggleMute]);

  const nudgeControls = useCallback(() => {
    setShowControls(true);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      if (!videoRef.current?.paused) setShowControls(false);
    }, 2600);
  }, []);

  if (!src) {
    return (
      <div className="flex aspect-video w-full items-center justify-center rounded-2xl bg-zinc-900 text-white/50">
        No video selected.
      </div>
    );
  }

  const activeLevelLabel =
    currentLevel === -1
      ? "Auto"
      : `${levels.find((l) => l.index === currentLevel)?.height ?? "?"}p`;

  return (
    <div
      ref={containerRef}
      onMouseMove={nudgeControls}
      onMouseLeave={() => !videoRef.current?.paused && setShowControls(false)}
      className="group relative aspect-video w-full select-none overflow-hidden rounded-2xl bg-black"
    >
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <video
        ref={videoRef}
        onClick={togglePlay}
        poster={poster ?? undefined}
        className="h-full w-full bg-black"
        playsInline
      />

      {/* Loading spinner */}
      {loading && !error && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <Loader2 className="h-12 w-12 animate-spin text-white/80" />
        </div>
      )}

      {/* Big center play (before start / when paused) */}
      {!playing && !loading && !error && (
        <button
          type="button"
          onClick={togglePlay}
          className="absolute inset-0 flex items-center justify-center"
        >
          <span className="flex h-20 w-20 items-center justify-center rounded-full bg-white/20 backdrop-blur-xl transition-transform hover:scale-105">
            <Play className="h-9 w-9 translate-x-0.5 fill-white text-white" />
          </span>
        </button>
      )}

      {/* Error overlay */}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/80 px-6 text-center">
          <p className="text-sm text-rose-300">{error}</p>
          <button
            type="button"
            onClick={() => {
              setError(null);
              const v = videoRef.current;
              if (v) {
                hlsRef.current?.recoverMediaError?.();
                void v.play();
              }
            }}
            className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-bold text-black"
          >
            <RotateCcw className="h-4 w-4" /> Retry
          </button>
        </div>
      )}

      {/* Title (top) */}
      {title && (started ? showControls : true) && (
        <div className="pointer-events-none absolute inset-x-0 top-0 bg-gradient-to-b from-black/70 to-transparent p-4">
          <h2 className="text-sm font-bold tracking-tight text-white">{title}</h2>
        </div>
      )}

      {/* Stats HUD */}
      {showStats && (
        <div className="absolute right-3 top-12 z-20 w-56 rounded-xl bg-black/75 p-3 text-[11px] text-white/80 backdrop-blur-xl">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-white/40">
            QoE
          </div>
          <ul className="space-y-0.5">
            <li>Startup: {startupMs != null ? `${startupMs} ms` : "—"}</li>
            <li>Bitrate: {bitrateKbps ? `${bitrateKbps} kbps` : "—"}</li>
            <li>Quality: {activeLevelLabel}</li>
            <li>Buffer: {Math.max(0, buffered - current).toFixed(1)} s</li>
            <li>Rebuffers: {rebuffers}</li>
          </ul>
        </div>
      )}

      {/* Control bar */}
      <div
        className={[
          "absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-8 transition-opacity",
          showControls || !playing ? "opacity-100" : "opacity-0",
        ].join(" ")}
      >
        {/* Scrubber */}
        <div className="relative mb-1.5 h-1.5">
          <div className="absolute inset-0 rounded-full bg-white/20" />
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-white/40"
            style={{ width: `${duration ? (buffered / duration) * 100 : 0}%` }}
          />
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-indigo-400"
            style={{ width: `${duration ? (current / duration) * 100 : 0}%` }}
          />
          <input
            type="range"
            min={0}
            max={duration || 0}
            step="0.1"
            value={current}
            onChange={(e) => seek(Number(e.target.value))}
            className="absolute inset-0 w-full cursor-pointer opacity-0"
            aria-label="Seek"
          />
        </div>

        <div className="flex items-center gap-3 text-white">
          <button type="button" onClick={togglePlay} aria-label="Play/Pause">
            {playing ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
          </button>

          <div className="flex items-center gap-2">
            <button type="button" onClick={toggleMute} aria-label="Mute">
              {muted || volume === 0 ? <VolumeX className="h-5 w-5" /> : <Volume2 className="h-5 w-5" />}
            </button>
            <input
              type="range"
              min={0}
              max={1}
              step="0.05"
              value={muted ? 0 : volume}
              onChange={(e) => {
                const v = videoRef.current;
                if (v) {
                  v.volume = Number(e.target.value);
                  v.muted = Number(e.target.value) === 0;
                }
              }}
              className="h-1 w-20 cursor-pointer accent-white"
              aria-label="Volume"
            />
          </div>

          <span className="text-xs tabular-nums text-white/80">
            {fmt(current)} / {fmt(duration)}
          </span>

          <div className="ml-auto flex items-center gap-2">
            {/* Quality */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenu(menu === "quality" ? null : "quality")}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold hover:bg-white/15"
              >
                <Settings className="h-4 w-4" /> {activeLevelLabel}
              </button>
              {menu === "quality" && (
                <div className="absolute bottom-9 right-0 min-w-[110px] rounded-lg bg-black/90 p-1 text-xs shadow-xl ring-1 ring-white/10">
                  <button
                    type="button"
                    onClick={() => setQuality(-1)}
                    className={`block w-full rounded px-2 py-1.5 text-left hover:bg-white/10 ${currentLevel === -1 ? "text-indigo-300" : ""}`}
                  >
                    Auto
                  </button>
                  {[...levels].reverse().map((l) => (
                    <button
                      key={l.index}
                      type="button"
                      onClick={() => setQuality(l.index)}
                      className={`block w-full rounded px-2 py-1.5 text-left hover:bg-white/10 ${currentLevel === l.index ? "text-indigo-300" : ""}`}
                    >
                      {l.height}p
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Speed */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenu(menu === "speed" ? null : "speed")}
                className="rounded px-2 py-1 text-xs font-semibold hover:bg-white/15"
              >
                {rate}×
              </button>
              {menu === "speed" && (
                <div className="absolute bottom-9 right-0 min-w-[70px] rounded-lg bg-black/90 p-1 text-xs shadow-xl ring-1 ring-white/10">
                  {[0.5, 1, 1.25, 1.5, 2].map((r) => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => setSpeed(r)}
                      className={`block w-full rounded px-2 py-1.5 text-left hover:bg-white/10 ${rate === r ? "text-indigo-300" : ""}`}
                    >
                      {r}×
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={() => setShowStats((s) => !s)}
              aria-label="Stats"
              className={`rounded p-1 hover:bg-white/15 ${showStats ? "text-indigo-300" : ""}`}
            >
              <Gauge className="h-4 w-4" />
            </button>

            <button type="button" onClick={toggleFullscreen} aria-label="Fullscreen">
              {fullscreen ? <Minimize className="h-5 w-5" /> : <Maximize className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
