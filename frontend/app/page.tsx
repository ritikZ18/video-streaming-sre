"use client";

import { useState, useMemo, useEffect } from "react";
import { Movie } from "../lib/types";
import { initialMovies } from "../data/movies";
import { listMovies } from "../lib/api";
import { Navbar } from "../components/layout/Navbar";
import { Footer } from "../components/layout/Footer";
import { HeroCarousel } from "../components/movie/HeroCarousel";
import { ScrollRow } from "../components/movie/ScrollRow";
import { MovieDetail } from "../components/movie/MovieDetail";

const GENRES = ["Trending", "Action", "Sci-Fi", "Drama", "Comedy", "Documentary"] as const;

export default function HomePage() {
  const [movies, setMovies] = useState<Movie[]>(initialMovies);
  const [selectedMovie, setSelectedMovie] = useState<Movie | null>(null);

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
    // Poll so processing → ready flips in the UI without a manual reload.
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

  const grouped = useMemo(() => {
    const result: Record<string, Movie[]> = {};
    GENRES.forEach((g) => {
      if (g === "Trending") {
        result[g] = movies.filter(
          (m) => m.tag === "Trending" || m.tag === "New Release",
        );
      } else {
        result[g] = movies.filter((m) => m.genre === g);
      }
    });
    return result;
  }, [movies]);

  return (
    <div className="min-h-screen bg-black text-white">
      <Navbar />
      <main className="relative z-0">
        <HeroCarousel movies={movies.filter((m) => m.tag === "Trending" || m.tag === "New Release")} onMoreInfo={setSelectedMovie} onPlay={playMovie} />
        <section className="px-8 pb-16">
          <ScrollRow
            title="Trending Now"
            movies={grouped["Trending"] ?? []}
            cardSize="large"
            onMovieClick={setSelectedMovie}
          />
          {GENRES.filter((g) => g !== "Trending").map((g) => (
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
