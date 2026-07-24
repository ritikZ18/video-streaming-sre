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
};

/**
 * Muted, looping HLS clip behind the hero that fades in over the still image
 * once it actually starts playing — and quietly falls back to the still if it
 * can't load. Reuses the app's hls.js setup pattern (native HLS on Safari, else
 * `new Hls()`); it does NOT touch VideoPlayer.tsx. Under prefers-reduced-motion
 * it skips autoplay entirely and shows only the still image.
 */
export function HeroBackdrop({ src, image, gradient }: HeroBackdropProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const reduce = useReducedMotion();

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src || reduce) return;
    setPlaying(false);

    let hls: Hls | null = null;
    const onPlaying = () => setPlaying(true);
    video.addEventListener("playing", onPlaying);

    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
      void video.play().catch(() => {});
    } else if (Hls.isSupported()) {
      hls = new Hls({ enableWorker: true });
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => void video.play().catch(() => {}));
      hls.on(Hls.Events.ERROR, (_e, d) => {
        if (d.fatal) setPlaying(false);
      });
    }
    return () => {
      video.removeEventListener("playing", onPlaying);
      if (hls) hls.destroy();
    };
  }, [src, reduce]);

  const still = image
    ? {
        backgroundImage: `url("${image}")`,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }
    : { backgroundImage: gradient ?? "#12121a" };

  return (
    <div className="absolute inset-0 overflow-hidden">
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
  );
}
