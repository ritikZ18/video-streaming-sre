import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MovieCard } from "../../components/movie/MovieCard";
import type { Movie } from "../../lib/types";

const movie: Movie = {
  id: 1,
  title: "Test Movie",
  genre: "Action",
  year: 2025,
  rating: "PG-13",
  duration: "2h 00m",
  description: "Test description",
  gradient: "linear-gradient(135deg,#000,#111)",
  accent: "#ffffff",
  tag: "Trending",
  streamUrl: null,
};

describe("MovieCard", () => {
  it("renders title and metadata", () => {
    const handleClick = vi.fn();
    render(<MovieCard movie={movie} onClick={handleClick} />);
    expect(screen.getByText("Test Movie")).toBeInTheDocument();
    expect(screen.getByText(/Action · 2025/)).toBeInTheDocument();
  });

  it("calls onClick when clicked", () => {
    const handleClick = vi.fn();
    render(<MovieCard movie={movie} onClick={handleClick} />);
    fireEvent.click(screen.getByText("Test Movie"));
    expect(handleClick).toHaveBeenCalledWith(movie);
  });
});

