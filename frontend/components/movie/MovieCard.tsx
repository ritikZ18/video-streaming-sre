"use client";

import { useState } from "react";
import type { Movie } from "../../lib/types";
import { Play } from "lucide-react";

type MovieCardProps = {
  movie: Movie;
  onClick: (movie: Movie) => void;
  size?: "normal" | "large";
};

export function MovieCard({ movie, onClick, size = "normal" }: MovieCardProps) {
  const [hovered, setHovered] = useState(false);
  const isLarge = size === "large";

  const baseClasses =
    "relative flex-shrink-0 cursor-pointer overflow-hidden rounded-card shadow-glow-soft transition-transform duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)]";

  const dims = isLarge ? "min-w-[350px] h-[200px]" : "min-w-[220px] h-[130px]";

  return (
    <div
      onClick={() => onClick(movie)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={
        movie.thumbnailUrl
          ? {
              backgroundImage: `url("${movie.thumbnailUrl}")`,
              backgroundSize: "cover",
              backgroundPosition: "center",
            }
          : { backgroundImage: movie.gradient }
      }
      className={`${baseClasses} ${dims} ${
        hovered ? "scale-105" : "scale-100"
      }`}
    >
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/40 to-black/5 transition-opacity" />

      {movie.tag && (
        <div className="absolute left-2.5 top-2.5 rounded-full bg-white/15 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white backdrop-blur-xl">
          {movie.tag}
        </div>
      )}

      <div className="absolute inset-x-3 bottom-3">
        <div className="truncate text-sm font-bold text-white">
          {movie.title}
        </div>
        <div className="text-[11px] font-medium text-white/60">
          {movie.genre} · {movie.year}
        </div>
      </div>

      {hovered && (
        <div className="absolute left-1/2 top-1/2 flex h-11 w-11 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white/25 backdrop-blur-xl">
          <Play className="h-4 w-4 fill-white text-white" />
        </div>
      )}
    </div>
  );
}

