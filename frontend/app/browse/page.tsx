"use client";

import { useEffect, useMemo, useState } from "react";
import { initialMovies } from "../../data/movies";
import type { Movie } from "../../lib/types";
import { listMovies } from "../../lib/api";
import { fetchTmdbCatalog } from "../../lib/tmdb";
import { dedupeByTitle } from "../../lib/catalog";
import { Navbar } from "../../components/layout/Navbar";
import { Footer } from "../../components/layout/Footer";
import { MovieCard } from "../../components/movie/MovieCard";
import { MovieDetail } from "../../components/movie/MovieDetail";
import { LiveRail } from "../../components/live/LiveRail";

const GENRES = ["All", "Action", "Sci-Fi", "Drama", "Comedy", "Documentary"] as const;

export default function BrowsePage() {
  const [uploads, setUploads] = useState<Movie[]>([]);
  const [catalog, setCatalog] = useState<Movie[]>(initialMovies);
  const [search, setSearch] = useState("");
  const [genre, setGenre] = useState<(typeof GENRES)[number]>("All");
  const [selected, setSelected] = useState<Movie | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      listMovies()
        .then((r) => {
          // Browse is public — show published titles only.
          if (active) setUploads(r.filter((m) => (m.visibility ?? "published") === "published"));
        })
        .catch(() => {});
    };
    load();
    const t = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, []);

  useEffect(() => {
    let active = true;
    fetchTmdbCatalog(500)
      .then((l) => {
        if (active && l.length) setCatalog(l);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const playMovie = (movie: Movie) => {
    if (!movie.manifestUrl) return;
    window.location.href = `/player?id=${encodeURIComponent(movie.id)}`;
  };

  const movies = useMemo(() => {
    const ids = new Set(uploads.map((m) => m.id));
    return dedupeByTitle([...uploads, ...catalog.filter((m) => !ids.has(m.id))]);
  }, [uploads, catalog]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return movies.filter((movie) => {
      const matchesGenre = genre === "All" || movie.genre === genre;
      const matchesQuery =
        !q ||
        movie.title.toLowerCase().includes(q) ||
        movie.genre.toLowerCase().includes(q);
      return matchesGenre && matchesQuery;
    });
  }, [movies, genre, search]);

  return (
    <div className="min-h-screen text-white">
      <Navbar />
      <main className="px-8 pt-24 pb-16">
        <LiveRail className="pb-6" />
        <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-heading">Browse</h1>
            <p className="text-sm text-white/60">
              {filtered.length} titles · explore by genre or search.
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
                      active ? "bg-white text-black" : "bg-transparent text-white/60 hover:text-white",
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
        <section className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] justify-items-center gap-x-4 gap-y-7">
          {filtered.map((movie) => (
            <MovieCard key={movie.id} movie={movie} onClick={setSelected} size="normal" />
          ))}
        </section>
      </main>
      <Footer />
      {selected && (
        <MovieDetail movie={selected} onClose={() => setSelected(null)} onPlay={playMovie} />
      )}
    </div>
  );
}
