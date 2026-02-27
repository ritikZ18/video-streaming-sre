"use client";

import { useState, useMemo } from "react";
import { Movie } from "../lib/types";
import { initialMovies } from "../data/movies";
import { Navbar } from "../components/layout/Navbar";
import { Footer } from "../components/layout/Footer";
import { HeroCarousel } from "../components/movie/HeroCarousel";
import { ScrollRow } from "../components/movie/ScrollRow";
import { MovieDetail } from "../components/movie/MovieDetail";

const GENRES = ["Trending", "Action", "Sci-Fi", "Drama", "Comedy", "Documentary"] as const;

export default function HomePage() {
  const [movies, setMovies] = useState<Movie[]>(initialMovies);
  const [selectedMovie, setSelectedMovie] = useState<Movie | null>(null);

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
      <Navbar onAddMovieClick={() => {}} />
      <main className="relative z-0">
        <HeroCarousel movies={movies.filter((m) => m.tag === "Trending" || m.tag === "New Release")} onMoreInfo={setSelectedMovie} />
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
        <MovieDetail movie={selectedMovie} onClose={() => setSelectedMovie(null)} />
      )}
    </div>
  );
}

