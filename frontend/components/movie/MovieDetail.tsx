"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import type { Movie } from "../../lib/types";
import { softSpring } from "../../lib/motion";

type MovieDetailProps = {
  movie: Movie;
  onClose: () => void;
  onPlay?: (movie: Movie) => void;
};

export function MovieDetail({ movie, onClose, onPlay }: MovieDetailProps) {
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-2xl"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 24, scale: 0.98 }}
          transition={softSpring}
          className="relative flex w-[90%] max-w-xl flex-col overflow-hidden rounded-modal border border-white/10 bg-zinc-900/70 shadow-2xl ring-1 ring-white/5 backdrop-blur-2xl backdrop-saturate-150"
          onClick={(event) => event.stopPropagation()}
        >
          <div
            className="relative h-64 bg-cover bg-center"
            style={
              movie.thumbnailUrl
                ? { backgroundImage: `url("${movie.thumbnailUrl}")` }
                : { backgroundImage: movie.gradient }
            }
          >
            <div className="absolute inset-0 bg-gradient-to-t from-zinc-900 to-transparent" />
            <button
              type="button"
              aria-label="Close"
              onClick={onClose}
              className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full bg-black/60 text-white backdrop-blur-xl"
            >
              <X className="h-4 w-4" />
            </button>
            {movie.tag && (
              <div className="absolute left-5 top-5 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold text-white backdrop-blur-xl">
                {movie.tag}
              </div>
            )}
            <div className="absolute bottom-6 left-6 right-6">
              <h1 className="text-[32px] font-extrabold tracking-tight text-white">
                {movie.title}
              </h1>
            </div>
          </div>
          <div className="space-y-4 px-7 pb-7 pt-5">
            <div className="flex flex-wrap gap-2">
              {[movie.year, movie.rating, movie.duration, movie.genre].map(
                (token) => (
                  <span
                    key={token}
                    className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-white/80"
                  >
                    {token}
                  </span>
                ),
              )}
            </div>
            <p className="text-sm leading-relaxed text-white/70">
              {movie.description}
            </p>
            <div className="flex gap-3 pt-1">
              <button
                type="button"
                onClick={() => onPlay?.(movie)}
                disabled={!onPlay || !movie.manifestUrl}
                title={movie.manifestUrl ? "Play" : "Still processing"}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-black transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span>{movie.status === "processing" ? "Processing…" : "Play"}</span>
              </button>
              <button
                type="button"
                aria-label="Add to my list"
                className="flex h-11 w-11 items-center justify-center rounded-xl border border-white/20 bg-white/10 text-white backdrop-blur-xl transition-colors hover:bg-white/20 focus-visible:ring-2 focus-visible:ring-white/60"
              >
                +
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

