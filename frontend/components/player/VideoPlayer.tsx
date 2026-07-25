"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { motion, AnimatePresence } from "framer-motion";
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
  Languages,
  Captions,
} from "lucide-react";
import { sendBeacon, type BeaconEvent } from "../../lib/api";
import type { SubtitleTrack } from "../../lib/types";

type VideoPlayerProps = {
  src: string | null;
  poster?: string | null;
  title?: string | null;
  contentId?: string | null;
  subtitleTracks?: SubtitleTrack[];
};

type Level = { index: number; height: number };
type AudioOpt = { index: number; label: string };
type Menu = null | "quality" | "audio" | "captions" | "speed";

function fmt(t: number): string {
  if (!Number.isFinite(t) || t < 0) return "0:00";
  const s = Math.floor(t % 60);
  const m = Math.floor((t / 60) % 60);
  const h = Math.floor(t / 3600);
  const mm = h > 0 ? String(m).padStart(2, "0") : String(m);
  return `${h > 0 ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

const menuAnim = {
  initial: { opacity: 0, y: 6, scale: 0.96 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: 6, scale: 0.96 },
  transition: { duration: 0.14 },
};

export function VideoPlayer({
  src,
  poster,
  title,
  contentId,
  subtitleTracks = [],
}: VideoPlayerProps) {
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
  const [loading, setLoading] = useState(false); // buffering / stalled only -> spinner
  const [error, setError] = useState<string | null>(null);
  const [showControls, setShowControls] = useState(true);
  const [menu, setMenu] = useState<Menu>(null);

  const [levels, setLevels] = useState<Level[]>([]);
  const [currentLevel, setCurrentLevel] = useState(-1);
  const [audioTracks, setAudioTracks] = useState<AudioOpt[]>([]);
  const [currentAudio, setCurrentAudio] = useState(0);
  const [currentCaption, setCurrentCaption] = useState(-1); // -1 = off
  const [rate, setRate] = useState(1);

  const [showStats, setShowStats] = useState(false);
  const [bitrateKbps, setBitrateKbps] = useState(0);
  const [rebuffers, setRebuffers] = useState(0);
  const [startupMs, setStartupMs] = useState<number | null>(null);
  const [playingHeight, setPlayingHeight] = useState(0); // actual rendition height, even in auto
  const [imax, setImax] = useState(false); // fill-screen (object-cover) mode

  const sessionRef = useRef("");
  const eventsRef = useRef<BeaconEvent[]>([]);
  const loadStartRef = useRef(0);
  const rebufferStartRef = useRef(0);
  const gotFirstRef = useRef(false);
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

  // ---- HLS ----
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;

    sessionRef.current =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `sess-${Math.floor(performance.now())}`;
    eventsRef.current = [];
    gotFirstRef.current = false;
    loadStartRef.current = performance.now();
    setError(null);
    setLevels([]);
    setAudioTracks([]);
    setCurrentLevel(-1);
    setLoading(false);

    let hls: Hls | null = null;
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
    } else if (Hls.isSupported()) {
      hls = new Hls({ enableWorker: true, lowLatencyMode: false, backBufferLength: 60 });
      hlsRef.current = hls;
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setLevels(hls!.levels.map((l, i) => ({ index: i, height: l.height })));
      });
      // Authoritative VOD duration straight from the media playlist (sum of
      // EXTINF). The <video>.duration can lag or read Infinity mid-load, which
      // left the seek bar dead at 0:00 — this fixes the scrubber + timer.
      hls.on(Hls.Events.LEVEL_LOADED, (_e, data) => {
        const d = data.details;
        if (d && !d.live && Number.isFinite(d.totalduration) && d.totalduration > 0) {
          setDuration(d.totalduration);
        }
      });
      hls.on(Hls.Events.AUDIO_TRACKS_UPDATED, () => {
        setAudioTracks(
          hls!.audioTracks.map((t, i) => ({
            index: i,
            label: t.name || t.lang || `Audio ${i + 1}`,
          })),
        );
        setCurrentAudio(hls!.audioTrack);
      });
      hls.on(Hls.Events.AUDIO_TRACK_SWITCHED, (_e, d) => setCurrentAudio(d.id));
      hls.on(Hls.Events.LEVEL_SWITCHED, (_e, data) => {
        const lvl = hls!.levels[data.level];
        if (lvl) {
          setBitrateKbps(Math.round((lvl.bitrate || 0) / 1000));
          setPlayingHeight(lvl.height || 0);
          setCurrentLevel(hls!.autoLevelEnabled ? -1 : data.level);
          pushEvent({ event: "bitrate_switch", current_bitrate_kbps: Math.round((lvl.bitrate || 0) / 1000) });
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
      // Ground truth from the element itself: keep React's playing/loading in
      // sync with reality even if the discrete play/playing events were missed
      // (that is what left the ▶ overlay up while the video was actually playing).
      setPlaying(!video.paused);
      if (!video.paused && video.currentTime > 0) {
        setLoading(false);
        // Fallback startup metric if the 'playing' event was missed.
        if (!gotFirstRef.current) {
          gotFirstRef.current = true;
          const ms = Math.round(performance.now() - loadStartRef.current);
          setStartupMs(ms);
          pushEvent({ event: "startup", startup_ms: ms });
        }
      }
    };
    // Only trust a finite duration (a live/unfinalized HLS reports Infinity).
    const onMeta = () => {
      if (Number.isFinite(video.duration)) setDuration(video.duration);
    };
    const onCanPlay = () => setLoading(false);
    // 'waiting'/'stalled' are the ONLY things that raise the spinner.
    const onWaiting = () => {
      setLoading(true);
      if (gotFirstRef.current) rebufferStartRef.current = performance.now();
    };
    const onPlaying = () => {
      setLoading(false);
      if (!gotFirstRef.current) {
        gotFirstRef.current = true;
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
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("timeupdate", onTime);
    video.addEventListener("loadedmetadata", onMeta);
    video.addEventListener("durationchange", onMeta);
    video.addEventListener("canplay", onCanPlay);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("playing", onPlaying);
    video.addEventListener("volumechange", onVol);
    return () => {
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("timeupdate", onTime);
      video.removeEventListener("loadedmetadata", onMeta);
      video.removeEventListener("durationchange", onMeta);
      video.removeEventListener("canplay", onCanPlay);
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("playing", onPlaying);
      video.removeEventListener("volumechange", onVol);
    };
  }, [pushEvent]);

  // Bulletproof state sync: poll the <video> element directly so the UI can
  // NEVER desync from reality (the ▶ overlay staying up while playing was a
  // missed-event desync). This is the source of truth for play/time/duration.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const id = setInterval(() => {
      setPlaying(!v.paused && !v.ended);
      setCurrent(v.currentTime);
      if (Number.isFinite(v.duration) && v.duration > 0) setDuration(v.duration);
      if (v.buffered.length) setBuffered(v.buffered.end(v.buffered.length - 1));
      // Derive the live rendition from hls.js directly — LEVEL_SWITCHED can be
      // missed, which left Quality at "Auto" and Bitrate blank.
      const hls = hlsRef.current;
      if (hls) {
        const idx = hls.currentLevel >= 0 ? hls.currentLevel : hls.loadLevel;
        const lvl = hls.levels?.[idx];
        if (lvl) {
          if (lvl.height) setPlayingHeight(lvl.height);
          if (lvl.bitrate) setBitrateKbps(Math.round(lvl.bitrate / 1000));
        }
      }
    }, 250);
    return () => clearInterval(id);
  }, [src]);

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

  useEffect(() => {
    const onFs = () => {
      const fs = Boolean(document.fullscreenElement);
      setFullscreen(fs);
      if (!fs) setImax(false); // leaving fullscreen exits IMAX fill
    };
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
    if (hlsRef.current) hlsRef.current.currentLevel = index;
    setCurrentLevel(index);
    setMenu(null);
  };
  const setAudio = (index: number) => {
    if (hlsRef.current) hlsRef.current.audioTrack = index;
    setCurrentAudio(index);
    setMenu(null);
  };
  const setCaption = (index: number) => {
    const v = videoRef.current;
    if (v) {
      for (let i = 0; i < v.textTracks.length; i += 1) {
        v.textTracks[i].mode = i === index ? "showing" : "disabled";
      }
    }
    setCurrentCaption(index);
    setMenu(null);
  };
  const setSpeed = (r: number) => {
    const v = videoRef.current;
    if (v) v.playbackRate = r;
    setRate(r);
    setMenu(null);
  };

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

  const nudge = useCallback(() => {
    setShowControls(true);
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      if (!videoRef.current?.paused && !menu) setShowControls(false);
    }, 2600);
  }, [menu]);

  if (!src) {
    return (
      <div className="flex aspect-video w-full items-center justify-center rounded-2xl bg-zinc-900 text-white/50">
        No video selected.
      </div>
    );
  }

  // "Auto · 720p" in auto (shows the rendition actually playing); "720p" when pinned.
  const qualityLabel =
    currentLevel === -1
      ? playingHeight
        ? `Auto · ${playingHeight}p`
        : "Auto"
      : `${levels.find((l) => l.index === currentLevel)?.height ?? playingHeight ?? "?"}p`;

  const menuBtn =
    "flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold hover:bg-white/15";
  const itemCls = (active: boolean) =>
    `block w-full rounded px-2 py-1.5 text-left hover:bg-white/10 ${active ? "text-indigo-300" : ""}`;

  return (
    <div
      ref={containerRef}
      onMouseMove={nudge}
      onMouseLeave={() => !videoRef.current?.paused && !menu && setShowControls(false)}
      className={`group relative w-full select-none overflow-hidden bg-black ${
        fullscreen
          ? "flex h-full items-center justify-center" // fill the whole screen — no 16:9 box, so IMAX can crop-fill edge to edge
          : "aspect-video rounded-2xl ring-1 ring-white/10"
      }`}
    >
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <video
        ref={videoRef}
        onClick={togglePlay}
        poster={poster ?? undefined}
        crossOrigin="anonymous"
        preload="auto"
        className={`h-full w-full bg-black ${imax ? "object-cover" : "object-contain"}`}
        playsInline
      >
        {subtitleTracks.map((t) => (
          <track key={t.url} kind="subtitles" src={t.url} srcLang={t.language} label={t.label} />
        ))}
      </video>

      {/* Spinner: ONLY while genuinely buffering / stalled. */}
      {!error && loading && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/20">
          <Loader2 className="h-12 w-12 animate-spin text-white/80" />
        </div>
      )}

      {/* Center Play button whenever paused (hidden as soon as it's playing). */}
      <AnimatePresence>
        {!error && !playing && !loading && (
          <motion.button
            type="button"
            onClick={togglePlay}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="absolute inset-0 flex items-center justify-center"
          >
            <span className="flex h-20 w-20 items-center justify-center rounded-full bg-white/20 backdrop-blur-xl transition-transform hover:scale-105">
              <Play className="h-9 w-9 translate-x-0.5 fill-white text-white" />
            </span>
          </motion.button>
        )}
      </AnimatePresence>

      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/80 px-6 text-center">
          <p className="text-sm text-rose-300">{error}</p>
          <button
            type="button"
            onClick={() => {
              setError(null);
              hlsRef.current?.recoverMediaError?.();
              void videoRef.current?.play();
            }}
            className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-bold text-black"
          >
            <RotateCcw className="h-4 w-4" /> Retry
          </button>
        </div>
      )}

      {title && (showControls || !playing) && (
        <div className="pointer-events-none absolute inset-x-0 top-0 bg-gradient-to-b from-black/70 to-transparent p-4">
          <h2 className="text-sm font-bold tracking-tight text-white">{title}</h2>
        </div>
      )}

      <AnimatePresence>
        {showStats && (
          <motion.div
            {...menuAnim}
            className="absolute right-3 top-12 z-20 w-56 rounded-xl bg-black/75 p-3 text-[11px] text-white/80 backdrop-blur-xl"
          >
            <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-white/40">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px] shadow-emerald-400" />
              Playback quality
            </div>
            <ul className="space-y-1">
              <li className="flex justify-between gap-4">
                <span className="text-white/45">Quality</span>
                <span className="font-medium text-white">{qualityLabel}</span>
              </li>
              <li className="flex justify-between gap-4">
                <span className="text-white/45">Bitrate</span>
                <span className="font-medium text-white">
                  {bitrateKbps ? `${(bitrateKbps / 1000).toFixed(1)} Mbps` : "—"}
                </span>
              </li>
              <li className="flex justify-between gap-4">
                <span className="text-white/45">Startup</span>
                <span className="font-medium text-white">
                  {startupMs != null ? `${startupMs} ms` : "—"}
                </span>
              </li>
              <li className="flex justify-between gap-4">
                <span className="text-white/45">Buffer</span>
                <span className="font-medium text-white">
                  {Math.max(0, buffered - current).toFixed(1)} s
                </span>
              </li>
              <li className="flex justify-between gap-4">
                <span className="text-white/45">Rebuffers</span>
                <span className="font-medium text-white">{rebuffers}</span>
              </li>
            </ul>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div
        animate={{ opacity: showControls || !playing ? 1 : 0 }}
        className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-8"
      >
        <div className="relative mb-1.5 h-1.5">
          <div className="absolute inset-0 rounded-full bg-white/20" />
          <div className="absolute inset-y-0 left-0 rounded-full bg-white/40" style={{ width: `${duration ? (buffered / duration) * 100 : 0}%` }} />
          <div className="absolute inset-y-0 left-0 rounded-full bg-indigo-400" style={{ width: `${duration ? (current / duration) * 100 : 0}%` }} />
          <input
            type="range" min={0} max={duration || 0} step="0.1" value={current}
            onChange={(e) => seek(Number(e.target.value))}
            className="absolute inset-0 w-full cursor-pointer opacity-0" aria-label="Seek"
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
              type="range" min={0} max={1} step="0.05" value={muted ? 0 : volume}
              onChange={(e) => {
                const v = videoRef.current;
                if (v) {
                  v.volume = Number(e.target.value);
                  v.muted = Number(e.target.value) === 0;
                }
              }}
              className="h-1 w-20 cursor-pointer accent-white" aria-label="Volume"
            />
          </div>
          <span className="text-xs tabular-nums text-white/80">{fmt(current)} / {fmt(duration)}</span>

          <div className="ml-auto flex items-center gap-1">
            {/* Audio / language */}
            {audioTracks.length > 1 && (
              <div className="relative">
                <button type="button" onClick={() => setMenu(menu === "audio" ? null : "audio")} className={menuBtn} aria-label="Audio">
                  <Languages className="h-4 w-4" />
                </button>
                <AnimatePresence>
                  {menu === "audio" && (
                    <motion.div {...menuAnim} className="absolute bottom-9 right-0 min-w-[140px] rounded-lg bg-black/90 p-1 text-xs shadow-xl ring-1 ring-white/10">
                      {audioTracks.map((a) => (
                        <button key={a.index} type="button" onClick={() => setAudio(a.index)} className={itemCls(currentAudio === a.index)}>
                          {a.label}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}

            {/* Captions */}
            {subtitleTracks.length > 0 && (
              <div className="relative">
                <button type="button" onClick={() => setMenu(menu === "captions" ? null : "captions")} className={`${menuBtn} ${currentCaption >= 0 ? "text-indigo-300" : ""}`} aria-label="Captions">
                  <Captions className="h-4 w-4" />
                </button>
                <AnimatePresence>
                  {menu === "captions" && (
                    <motion.div {...menuAnim} className="absolute bottom-9 right-0 min-w-[140px] rounded-lg bg-black/90 p-1 text-xs shadow-xl ring-1 ring-white/10">
                      <button type="button" onClick={() => setCaption(-1)} className={itemCls(currentCaption === -1)}>Off</button>
                      {subtitleTracks.map((t, i) => (
                        <button key={t.url} type="button" onClick={() => setCaption(i)} className={itemCls(currentCaption === i)}>
                          {t.label}
                        </button>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}

            {/* Quality */}
            <div className="relative">
              <button type="button" onClick={() => setMenu(menu === "quality" ? null : "quality")} className={menuBtn}>
                <Settings className="h-4 w-4" /> {qualityLabel}
              </button>
              <AnimatePresence>
                {menu === "quality" && (
                  <motion.div {...menuAnim} className="absolute bottom-9 right-0 min-w-[110px] rounded-lg bg-black/90 p-1 text-xs shadow-xl ring-1 ring-white/10">
                    <button type="button" onClick={() => setQuality(-1)} className={itemCls(currentLevel === -1)}>Auto</button>
                    {[...levels].reverse().map((l) => (
                      <button key={l.index} type="button" onClick={() => setQuality(l.index)} className={itemCls(currentLevel === l.index)}>
                        {l.height}p
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Speed */}
            <div className="relative">
              <button type="button" onClick={() => setMenu(menu === "speed" ? null : "speed")} className="rounded px-2 py-1 text-xs font-semibold hover:bg-white/15">{rate}×</button>
              <AnimatePresence>
                {menu === "speed" && (
                  <motion.div {...menuAnim} className="absolute bottom-9 right-0 min-w-[70px] rounded-lg bg-black/90 p-1 text-xs shadow-xl ring-1 ring-white/10">
                    {[0.5, 1, 1.25, 1.5, 2].map((r) => (
                      <button key={r} type="button" onClick={() => setSpeed(r)} className={itemCls(rate === r)}>{r}×</button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <button type="button" onClick={() => setShowStats((s) => !s)} aria-label="Stats" className={`rounded p-1 hover:bg-white/15 ${showStats ? "text-indigo-300" : ""}`}>
              <Gauge className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => {
                const el = containerRef.current;
                if (!imax) {
                  setImax(true);
                  if (el && !document.fullscreenElement) void el.requestFullscreen().catch(() => {});
                } else {
                  setImax(false);
                  if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
                }
              }}
              aria-label="IMAX fill mode"
              title={imax ? "Exit IMAX" : "IMAX — fullscreen, fills the whole screen (crops, never stretches)"}
              className={`rounded px-1.5 py-1 text-[11px] font-extrabold tracking-wide hover:bg-white/15 ${imax ? "text-indigo-300" : "text-white/80"}`}
            >
              IMAX
            </button>
            <button type="button" onClick={toggleFullscreen} aria-label="Fullscreen">
              {fullscreen ? <Minimize className="h-5 w-5" /> : <Maximize className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
