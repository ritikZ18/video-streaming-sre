"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Movie } from "../../lib/types";
import { Play } from "lucide-react";

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

  useEffect(() => {
    if (!featured.length) return;
    const timer = setInterval(
      () => setIndex((prev) => (prev + 1) % featured.length),
      6000,
    );
    return () => clearInterval(timer);
  }, [featured.length]);

  if (!featured.length) return null;

  const current = featured[index];

  return (
    <section className="relative h-[520px] overflow-hidden">
      <AnimatePresence mode="wait">
        <motion.div
          key={current.id}
          initial={{ opacity: 0, scale: 1.05 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 1.02 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="absolute inset-0 bg-cover bg-center"
          style={
            current.thumbnailUrl
              ? { backgroundImage: `url("${current.thumbnailUrl}")` }
              : { backgroundImage: current.gradient }
          }
        >
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,rgba(0,0,0,0.1),rgba(0,0,0,0.9))]" />
          <div className="absolute inset-x-0 bottom-0 h-64 bg-gradient-to-t from-black via-black/60 to-transparent" />
        </motion.div>
      </AnimatePresence>

      <div className="relative z-10 flex h-full items-end px-10 pb-24">
        <div className="max-w-xl animate-slideUp space-y-3">
          {current.tag && (
            <span className="inline-flex rounded-full bg-white/15 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-white backdrop-blur-xl">
              {current.tag}
            </span>
          )}
          <h1 className="text-[44px] font-extrabold leading-tight tracking-tight text-white">
            {current.title}
          </h1>
          <p className="text-sm font-medium text-white/70">
            {current.genre} · {current.year} · {current.rating} ·{" "}
            {current.duration}
          </p>
          <p className="max-w-xl text-sm leading-relaxed text-white/60">
            {current.description}
          </p>
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => onPlay?.(current)}
              disabled={!onPlay || !current.manifestUrl}
              title={current.manifestUrl ? "Play" : "Still processing"}
              className="inline-flex items-center gap-2 rounded-xl bg-white px-6 py-2.5 text-sm font-bold text-black shadow-glow-soft transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Play className="h-4 w-4 fill-black text-black" />
              {current.status === "processing" ? "Processing…" : "Play"}
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
                  ? "w-6 bg-white"
                  : "w-2 bg-white/40 hover:bg-white/70"
              }`}
            />
          );
        })}
      </div>
    </section>
  );
}

