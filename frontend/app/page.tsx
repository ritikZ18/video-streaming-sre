"use client";

import { useState, useMemo, useEffect } from "react";
import { Movie } from "../lib/types";
import { initialMovies } from "../data/movies";
import { listMovies } from "../lib/api";
import { fetchTmdbCatalog } from "../lib/tmdb";
import { dedupeByTitle } from "../lib/catalog";
import { Navbar } from "../components/layout/Navbar";
import { Footer } from "../components/layout/Footer";
import { HeroCarousel } from "../components/movie/HeroCarousel";
import { ScrollRow } from "../components/movie/ScrollRow";
import { MovieDetail } from "../components/movie/MovieDetail";

const GENRES = ["Action", "Sci-Fi", "Drama", "Comedy", "Documentary"] as const;

export default function HomePage() {
  const [uploads, setUploads] = useState<Movie[]>([]);
  const [catalog, setCatalog] = useState<Movie[]>(initialMovies);
  const [selectedMovie, setSelectedMovie] = useState<Movie | null>(null);

  // Playable uploads — poll so processing → ready flips live.
  useEffect(() => {
    let active = true;
    const load = () => {
      listMovies()
        .then((real) => {
          if (active) setUploads(real);
        })
        .catch(() => {
          /* catalog API unreachable — keep what we have */
        });
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  // TMDB catalog (display-only) — fetched once; falls back to the seed list.
  useEffect(() => {
    let active = true;
    fetchTmdbCatalog(500)
      .then((list) => {
        if (active && list.length) setCatalog(list);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const playMovie = (movie: Movie) => {
    if (!movie.manifestUrl) return;
    // Only the id — the player fetches url/title/poster via getMovie(id), so the
    // manifest/poster URLs aren't exposed in the address bar.
    window.location.href = `/player?id=${encodeURIComponent(movie.id)}`;
  };

  const dedupedUploads = useMemo(() => dedupeByTitle(uploads), [uploads]);

  // Uploads (playable) win over catalog entries by id; then collapse duplicate
  // titles so the same video can't appear across multiple genre rows.
  const movies = useMemo(() => {
    const ids = new Set(uploads.map((m) => m.id));
    return dedupeByTitle([...uploads, ...catalog.filter((m) => !ids.has(m.id))]);
  }, [uploads, catalog]);

  const grouped = useMemo(() => {
    const r: Record<string, Movie[]> = {};
    for (const g of GENRES) r[g] = movies.filter((m) => m.genre === g);
    return r;
  }, [movies]);

  const featured = useMemo(() => {
    const withArt = movies.filter((m) => m.backdropUrl);
    return (withArt.length ? withArt : movies).slice(0, 6);
  }, [movies]);

  return (
    <div className="min-h-screen text-white">
      <Navbar />
      <main className="relative z-0">
        <HeroCarousel movies={featured} onMoreInfo={setSelectedMovie} onPlay={playMovie} />
        <section className="px-8 pb-16 pt-2">
          {dedupedUploads.length > 0 && (
            <ScrollRow
              title="Your Library"
              movies={dedupedUploads}
              cardSize="large"
              onMovieClick={setSelectedMovie}
            />
          )}
          {GENRES.map((g) => (
            <ScrollRow
              key={g}
              title={g}
              movies={grouped[g] ?? []}
              cardSize="normal"
              onMovieClick={setSelectedMovie}
            />
          ))}
        </section>
      </main>
      <Footer />
      {selectedMovie && (
        <MovieDetail movie={selectedMovie} onClose={() => setSelectedMovie(null)} onPlay={playMovie} />
      )}
    </div>
  );
}
