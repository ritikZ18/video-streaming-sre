"use client";

import { useRef } from "react";
import { motion, useReducedMotion, type Variants } from "framer-motion";
import type { Movie } from "../../lib/types";
import { springy } from "../../lib/motion";

type MovieCardProps = {
  movie: Movie;
  onClick: (movie: Movie) => void;
  size?: "normal" | "large";
};

const REST_SHADOW =
  "0 8px 22px -12px rgba(0,0,0,0.9), 0 0 0 1px rgba(255,255,255,0.05), inset 0 1px 0 rgba(255,255,255,0)";
const FOCUS_SHADOW =
  "0 26px 44px -18px rgba(0,0,0,0.85), 0 0 0 1px rgba(255,255,255,0.10), inset 0 1px 0 rgba(255,255,255,0.14)";

export function MovieCard({ movie, onClick, size = "normal" }: MovieCardProps) {
  const posterRef = useRef<HTMLDivElement | null>(null);
  const reduce = useReducedMotion();
  const isLarge = size === "large";

  // Pointer-tracked specular highlight — set CSS vars directly (no re-render).
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = posterRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${((e.clientX - r.left) / r.width) * 100}%`);
    el.style.setProperty("--my", `${((e.clientY - r.top) / r.height) * 100}%`);
  };

  // Parent drives child variants via framer's label propagation ("off" → "on").
  const posterV: Variants = {
    off: { y: 0, scale: 1, boxShadow: REST_SHADOW },
    on: reduce
      ? { y: 0, scale: 1, boxShadow: FOCUS_SHADOW }
      : { y: -8, scale: 1.07, boxShadow: FOCUS_SHADOW },
  };
  const layerV: Variants = { off: { opacity: 0 }, on: { opacity: 1 } };
  // NOTE: mockup hides the caption until focus, but our catalog uses synthesized
  // gradient posters (no real art), so a hidden title = unidentifiable. Keep it
  // dim and brighten on focus instead.
  const capV: Variants = {
    off: { opacity: 0.72, y: 0 },
    on: { opacity: 1, y: 0 },
  };

  return (
    <motion.div
      className={`group ${isLarge ? "w-[190px]" : "w-[150px]"} flex-shrink-0 cursor-pointer rounded-poster outline-none focus-visible:ring-2 focus-visible:ring-white/60`}
      role="button"
      tabIndex={0}
      aria-label={`Open ${movie.title}`}
      initial="off"
      animate="off"
      whileHover="on"
      whileFocus="on"
      onClick={() => onClick(movie)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(movie);
        } else if (e.key === "ArrowRight") {
          e.preventDefault();
          (e.currentTarget.nextElementSibling as HTMLElement | null)?.focus();
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          (e.currentTarget.previousElementSibling as HTMLElement | null)?.focus();
        }
      }}
    >
      <motion.div
        ref={posterRef}
        onPointerMove={onPointerMove}
        variants={posterV}
        transition={springy}
        style={{ backgroundImage: movie.gradient }}
        className="relative aspect-[2/3] w-full overflow-hidden rounded-poster bg-surface-1 bg-cover bg-center ring-1 ring-white/[0.06]"
      >
        {/* Real poster over the gradient fallback; lazy so 500 cards don't all fetch. */}
        {movie.thumbnailUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={movie.thumbnailUrl}
            alt=""
            loading="lazy"
            className="absolute inset-0 h-full w-full object-cover"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.visibility = "hidden";
            }}
          />
        )}

        {/* Subtle diagonal glass sheen (fades in on focus). */}
        <motion.div
          variants={layerV}
          transition={{ duration: 0.35 }}
          className="pointer-events-none absolute inset-0 z-[2] rounded-poster"
          style={{
            backgroundImage:
              "linear-gradient(135deg, rgba(255,255,255,0.16), rgba(255,255,255,0.03) 42%, transparent 60%)",
          }}
        />

        {/* Pointer-tracked specular shine (screen blend, gentle). */}
        <motion.div
          variants={layerV}
          transition={{ duration: 0.4 }}
          className="pointer-events-none absolute inset-0 z-[3] rounded-poster"
          style={{
            mixBlendMode: "screen",
            background:
              "radial-gradient(140px 140px at var(--mx,50%) var(--my,50%), rgba(255,255,255,0.28), rgba(255,255,255,0.04) 45%, transparent 64%)",
          }}
        />
      </motion.div>

      {/* Caption below the poster, revealed on focus. */}
      <motion.div variants={capV} transition={springy} className="mt-2.5 px-0.5 text-center">
        <div className="truncate text-[13.5px] font-medium tracking-bodytight text-white">
          {movie.title}
        </div>
        <div className="text-[12px] text-ink-3">
          {movie.genre} · {movie.year}
        </div>
      </motion.div>
    </motion.div>
  );
}
