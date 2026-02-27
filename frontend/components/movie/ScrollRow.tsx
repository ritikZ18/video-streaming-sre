"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Movie } from "../../lib/types";
import { MovieCard } from "./MovieCard";

type ScrollRowProps = {
  title: string;
  movies: Movie[];
  onMovieClick: (movie: Movie) => void;
  cardSize?: "normal" | "large";
};

export function ScrollRow({
  title,
  movies,
  onMovieClick,
  cardSize = "normal",
}: ScrollRowProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [showLeft, setShowLeft] = useState(false);
  const [showRight, setShowRight] = useState(true);

  const checkScroll = () => {
    const node = scrollRef.current;
    if (!node) return;
    const { scrollLeft, scrollWidth, clientWidth } = node;
    setShowLeft(scrollLeft > 10);
    setShowRight(scrollLeft < scrollWidth - clientWidth - 10);
  };

  const scroll = (dir: 1 | -1) => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollBy({ left: dir * 400, behavior: "smooth" });
  };

  useEffect(() => {
    checkScroll();
  }, [movies.length]);

  if (!movies.length) return null;

  return (
    <div className="relative mb-9">
      <h2 className="mb-3 text-[20px] font-bold tracking-tight text-white">
        {title}
      </h2>
      <div className="relative">
        {showLeft && (
          <button
            type="button"
            onClick={() => scroll(-1)}
            className="absolute left-[-10px] top-1/2 z-10 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border-none bg-black/70 text-white backdrop-blur-xl"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
        )}
        <div
          ref={scrollRef}
          onScroll={checkScroll}
          className="flex gap-3 overflow-x-auto pb-2 [scrollbar-width:none]"
        >
          {movies.map((movie) => (
            <MovieCard
              key={movie.id}
              movie={movie}
              onClick={onMovieClick}
              size={cardSize}
            />
          ))}
        </div>
        {showRight && movies.length > 3 && (
          <button
            type="button"
            onClick={() => scroll(1)}
            className="absolute right-[-10px] top-1/2 z-10 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border-none bg-black/70 text-white backdrop-blur-xl"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        )}
      </div>
    </div>
  );
}

