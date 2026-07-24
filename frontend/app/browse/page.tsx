"use client";

import { useEffect, useMemo, useState } from "react";
import { initialMovies } from "../../data/movies";
import type { Movie } from "../../lib/types";
import { listMovies } from "../../lib/api";
import { Navbar } from "../../components/layout/Navbar";
import { Footer } from "../../components/layout/Footer";
import { MovieCard } from "../../components/movie/MovieCard";

const GENRES = ["All", "Action", "Sci-Fi", "Drama", "Comedy", "Documentary"] as const;

export default function BrowsePage() {
  const [movies, setMovies] = useState<Movie[]>(initialMovies);
  const [search, setSearch] = useState("");
  const [genre, setGenre] = useState<(typeof GENRES)[number]>("All");

  useEffect(() => {
    let active = true;
    const load = () => {
      listMovies()
        .then((real) => {
          if (!active) return;
          const realIds = new Set(real.map((m) => m.id));
          setMovies([...real, ...initialMovies.filter((s) => !realIds.has(s.id))]);
        })
        .catch(() => {
          /* Catalog API unreachable — keep the seed catalog. */
        });
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const playMovie = (movie: Movie) => {
    if (!movie.manifestUrl) return;
    const q = new URLSearchParams({ url: movie.manifestUrl, title: movie.title, id: movie.id });
    if (movie.thumbnailUrl) q.set("poster", movie.thumbnailUrl);
    window.location.href = `/player?${q.toString()}`;
  };

  const filtered = useMemo(() => {
    return movies.filter((movie) => {
      const matchesGenre = genre === "All" || movie.genre === genre;
      const q = search.toLowerCase();
      const matchesQuery =
        !q ||
        movie.title.toLowerCase().includes(q) ||
        movie.genre.toLowerCase().includes(q);
      return matchesGenre && matchesQuery;
    });
  }, [movies, genre, search]);

  return (
    <div className="min-h-screen bg-black text-white">
      <Navbar />
      <main className="px-8 pt-24 pb-16">
        <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Browse</h1>
            <p className="text-sm text-white/60">
              Explore the catalog by genre or search by title.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex gap-1 rounded-lg bg-white/5 p-1">
              {GENRES.map((g) => {
                const active = g === genre;
                return (
                  <button
                    key={g}
                    type="button"
                    onClick={() => setGenre(g)}
                    className={[
                      "rounded-md px-3 py-1 text-xs font-semibold transition-colors",
                      active
                        ? "bg-white text-black"
                        : "bg-transparent text-white/60 hover:text-white",
                    ].join(" ")}
                  >
                    {g}
                  </button>
                );
              })}
            </div>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search titles..."
              className="w-48 rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white outline-none placeholder:text-white/30 focus:border-white/40"
            />
          </div>
        </div>
        <section className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
          {filtered.map((movie) => (
            <MovieCard
              key={movie.id}
              movie={movie}
              onClick={playMovie}
              size="normal"
            />
          ))}
        </section>
      </main>
      <Footer />
    </div>
  );
}
