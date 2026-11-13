"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Movie } from "../../lib/types";
import { Play } from "lucide-react";
import { HeroBackdrop } from "./HeroBackdrop";
import { softSpring } from "../../lib/motion";

type HeroCarouselProps = {
  movies: Movie[];
  onMoreInfo: (movie: Movie) => void;
  onPlay?: (movie: Movie) => void;
};

export function HeroCarousel({ movies, onMoreInfo, onPlay }: HeroCarouselProps) {
  const featured = useMemo(
    () => (movies.length ? movies : []),
    [movies],
  );
  const [index, setIndex] = useState(0);
  const [videoPlaying, setVideoPlaying] = useState(false);
  // Mouse "active" in the hero → keep the title bright; idle → let it dim under
  // the playing clip. Resets a couple seconds after the last movement.
  const [active, setActive] = useState(false);
  const idleRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const markActive = () => {
    setActive(true);
    if (idleRef.current) clearTimeout(idleRef.current);
    idleRef.current = setTimeout(() => setActive(false), 2000);
  };
  const clearActive = () => {
    if (idleRef.current) clearTimeout(idleRef.current);
    setActive(false);
  };

  useEffect(() => {
    if (!featured.length) return;
    const timer = setInterval(
      () => setIndex((prev) => (prev + 1) % featured.length),
      6000,
    );
    return () => clearInterval(timer);
  }, [featured.length]);

  useEffect(() => () => {
    if (idleRef.current) clearTimeout(idleRef.current);
  }, []);

  if (!featured.length) return null;

  const current = featured[index];
  const dimText = videoPlaying && !active;

  return (
    <section
      className="relative h-[88svh] min-h-[560px] overflow-hidden"
      onMouseEnter={markActive}
      onMouseMove={markActive}
      onMouseLeave={clearActive}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={current.id}
          initial={{ opacity: 0, scale: 1.05 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 1.02 }}
          transition={softSpring}
          className="absolute inset-0"
        >
          <HeroBackdrop
            src={current.manifestUrl}
            image={current.backdropUrl ?? current.thumbnailUrl}
            gradient={current.gradient}
            onPlayingChange={setVideoPlaying}
          />
          {/* readability scrim — blended to the deep-navy page base (#0a0f1e) */}
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_28%_45%,rgba(0,0,0,0.05),rgba(10,15,30,0.86))]" />
          {/* rich cinematic base — a cool blue glow rising from bottom-left and a
              violet one from bottom-right; balanced, no single harsh corner */}
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(48%_42%_at_2%_100%,rgba(56,99,235,0.24),transparent_60%),radial-gradient(44%_40%_at_100%_100%,rgba(168,85,247,0.20),transparent_62%)]" />
          {/* feather the bottom edge: progressive blur so the media melts into
              the page rather than ending on a hard line */}
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 h-64 backdrop-blur-[6px]"
            style={{
              WebkitMaskImage: "linear-gradient(to top, #000 0%, #000 24%, transparent 100%)",
              maskImage: "linear-gradient(to top, #000 0%, #000 24%, transparent 100%)",
            }}
          />
          {/* …then fade fully into the deep-navy base */}
          <div className="absolute inset-x-0 bottom-0 h-96 bg-[linear-gradient(to_top,#0a0f1e_0%,rgba(10,15,30,0.86)_42%,transparent_100%)]" />
        </motion.div>
      </AnimatePresence>

      <div className="relative z-10 flex h-full items-end px-10 pb-28">
        <div className="max-w-xl animate-slideUp space-y-4">
          {/* Text group dims a little while the clip plays, unless the mouse is
              active in the hero — then it snaps back to full brightness. */}
          <div
            className={`space-y-3 transition-opacity duration-500 ${
              dimText ? "opacity-50" : "opacity-100"
            }`}
          >
            {current.tag && (
              <span className="inline-flex rounded-full border border-indigo-400/30 bg-indigo-500/20 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-indigo-100 backdrop-blur-xl">
                {current.tag}
              </span>
            )}
            <h1 className="text-[52px] font-bold leading-[0.98] tracking-display text-white">
              {current.title}
            </h1>
            <p className="text-sm font-medium text-white/70">
              {current.genre} · {current.year} · {current.rating} ·{" "}
              {current.duration}
            </p>
            <p className="line-clamp-2 max-w-xl text-sm leading-relaxed text-white/60">
              {current.description}
            </p>
          </div>
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => onPlay?.(current)}
              disabled={!onPlay || !current.manifestUrl}
              title={current.manifestUrl ? "Play" : "Still processing"}
              className="inline-flex items-center gap-2 rounded-xl bg-white px-6 py-2.5 text-sm font-bold text-black shadow-glow-soft transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Play className="h-4 w-4 fill-black text-black" />
              {/* Playable as soon as a manifest exists (a background re-encode
                  keeps the old segments streamable). Only a real upload still
                  encoding shows "Processing"; display-only catalog items don't. */}
              {!current.manifestUrl && current.status === "processing" && !current.displayOnly
                ? "Processing…"
                : "Play"}
            </button>
            <button
              type="button"
              onClick={() => onMoreInfo(current)}
              className="inline-flex items-center gap-2 rounded-xl border border-white/25 bg-white/10 px-5 py-2.5 text-sm font-semibold text-white backdrop-blur-xl transition-colors hover:bg-white/20"
            >
              More Info
            </button>
          </div>
        </div>
      </div>

      <div className="absolute bottom-6 left-1/2 z-10 flex -translate-x-1/2 gap-2">
        {featured.map((movie, idx) => {
          const active = idx === index;
          return (
            <button
              key={movie.id}
              type="button"
              onClick={() => setIndex(idx)}
              className={`h-2 rounded-full transition-all ${
                active
                  ? "w-7 bg-gradient-to-r from-indigo-400 to-fuchsia-400 shadow-glow-accent"
                  : "w-2 bg-white/40 hover:bg-white/70"
              }`}
            />
          );
        })}
      </div>
    </section>
  );
}

