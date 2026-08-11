"use client";

import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { useReducedMotion } from "framer-motion";

type HeroBackdropProps = {
  /** HLS manifest to preview behind the hero (muted, looping). */
  src?: string | null;
  /** Still image shown always + used as the fallback. */
  image?: string | null;
  /** Gradient fallback when there is no image. */
  gradient?: string;
  /** Fires true once the clip is actually playing, false otherwise. Pass a
      stable setter (e.g. a useState dispatcher) — it's in the effect deps. */
  onPlayingChange?: (playing: boolean) => void;
};

/**
 * Muted, looping HLS clip behind the hero that fades in over the still image
 * once it actually starts playing — and quietly falls back to the still if it
 * can't load. Reuses the app's hls.js setup pattern (native HLS on Safari, else
 * `new Hls()`); it does NOT touch VideoPlayer.tsx. Under prefers-reduced-motion
 * it skips autoplay entirely and shows only the still image.
 */
export function HeroBackdrop({ src, image, gradient, onPlayingChange }: HeroBackdropProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const reduce = useReducedMotion();

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src || reduce) return;
    const setP = (v: boolean) => {
      setPlaying(v);
      onPlayingChange?.(v);
    };
    setP(false);

    let hls: Hls | null = null;

    // Show a random ~6s slice from the MIDDLE of the clip (not the intro/black
    // frames), and a different slice on each mount so the hero feels alive.
    const CLIP = 6;
    let winStart = 0;
    let hasWindow = false;
    const pickWindow = () => {
      const d = video.duration;
      if (!isFinite(d) || d < CLIP + 4) return; // too short — just loop it whole
      const lo = d * 0.2;
      const hi = Math.max(lo, d * 0.85 - CLIP);
      winStart = lo + Math.random() * (hi - lo);
      hasWindow = true;
      try {
        video.currentTime = winStart;
      } catch {
        /* not seekable yet — timeupdate will re-anchor */
      }
    };
    const onLoadedMeta = () => pickWindow();
    const onTime = () => {
      if (hasWindow && (video.currentTime >= winStart + CLIP || video.currentTime < winStart - 0.5)) {
        try {
          video.currentTime = winStart;
        } catch {
          /* ignore transient seek errors */
        }
      }
    };

    const onPlaying = () => setP(true);
    video.addEventListener("playing", onPlaying);
    video.addEventListener("loadedmetadata", onLoadedMeta);
    video.addEventListener("timeupdate", onTime);

    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
      void video.play().catch(() => {});
    } else if (Hls.isSupported()) {
      hls = new Hls({ enableWorker: true, capLevelToPlayerSize: false });
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        // Hero should look pristine: lock to the sharpest rendition that ISN'T
        // 4K — the highest height under 2160p (tie-break on bitrate). Caps ABR
        // so it can't climb into 2160p, then loads that level immediately.
        const levels = hls!.levels;
        let target = -1;
        let best = { h: -1, bitrate: -1 };
        levels.forEach((lvl, i) => {
          const h = lvl.height || 0;
          if (h > 0 && h < 2160 && (h > best.h || (h === best.h && lvl.bitrate > best.bitrate))) {
            best = { h, bitrate: lvl.bitrate };
            target = i;
          }
        });
        if (target >= 0) {
          hls!.autoLevelCapping = target;
          hls!.currentLevel = target;
        }
        void video.play().catch(() => {});
      });
      hls.on(Hls.Events.ERROR, (_e, d) => {
        if (d.fatal) setP(false);
      });
    }
    return () => {
      video.removeEventListener("playing", onPlaying);
      video.removeEventListener("loadedmetadata", onLoadedMeta);
      video.removeEventListener("timeupdate", onTime);
      if (hls) hls.destroy();
    };
  }, [src, reduce, onPlayingChange]);

  const still = image
    ? {
        backgroundImage: `url("${image}")`,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }
    : { backgroundImage: gradient ?? "#12121a" };

  return (
    <div className="absolute inset-0 overflow-hidden">
      {/* Overscanned + nudged down so the framing sits lower in the hero
          (the "pull the video port down" ask) without exposing a top edge. */}
      <div className="absolute inset-0 scale-[1.14] translate-y-[6%]">
        <div className="absolute inset-0 bg-cover bg-center" style={still} />
        {!reduce && src && (
          <video
            ref={videoRef}
            muted
            loop
            playsInline
            preload="auto"
            aria-hidden="true"
            className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-1000 ${
              playing ? "opacity-100" : "opacity-0"
            }`}
          />
        )}
      </div>
    </div>
  );
}
