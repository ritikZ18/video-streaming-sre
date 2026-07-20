import type { Movie } from "../lib/types";

// Seed/demo catalog. Shown as a fallback when the catalog API is empty or
// unreachable (e.g. before floci + the pipeline have produced anything). Real
// uploads come from the Upload API and are merged in ahead of these.
export const initialMovies: Movie[] = [
  {
    id: "seed-aurora",
    title: "Aurora Drift",
    genre: "Sci-Fi",
    year: 2025,
    rating: "PG-13",
    duration: "1h 58m",
    description:
      "A stranded pilot rides the aurora currents home across a shattered orbital ring.",
    tag: "Trending",
    gradient: "linear-gradient(135deg,#312e81,#06b6d4)",
    status: "ready",
    manifestUrl: null,
  },
  {
    id: "seed-redline",
    title: "Redline County",
    genre: "Action",
    year: 2024,
    rating: "R",
    duration: "2h 12m",
    description:
      "A retired driver is pulled back for one last run through a city that never forgave her.",
    tag: "New Release",
    gradient: "linear-gradient(135deg,#be123c,#f59e0b)",
    status: "ready",
    manifestUrl: null,
  },
  {
    id: "seed-quietwater",
    title: "Quiet Water",
    genre: "Drama",
    year: 2023,
    rating: "PG",
    duration: "1h 44m",
    description:
      "Two estranged siblings restore their late father's lake house over one long summer.",
    tag: "Award Winner",
    gradient: "linear-gradient(135deg,#065f46,#22d3ee)",
    status: "ready",
    manifestUrl: null,
  },
  {
    id: "seed-lastlaugh",
    title: "The Last Laugh",
    genre: "Comedy",
    year: 2025,
    rating: "PG-13",
    duration: "1h 36m",
    description:
      "A washed-up comic accidentally becomes the mayor of the town that booed him off stage.",
    tag: "Popular",
    gradient: "linear-gradient(135deg,#4c1d95,#ec4899)",
    status: "ready",
    manifestUrl: null,
  },
  {
    id: "seed-deepfield",
    title: "Deep Field",
    genre: "Documentary",
    year: 2024,
    rating: "G",
    duration: "52m",
    description:
      "The decade-long build of a telescope designed to photograph the universe's first light.",
    tag: "Editor's Pick",
    gradient: "linear-gradient(135deg,#0f766e,#84cc16)",
    status: "ready",
    manifestUrl: null,
  },
  {
    id: "seed-nightmarket",
    title: "Night Market",
    genre: "Drama",
    year: 2022,
    rating: "PG-13",
    duration: "1h 51m",
    description:
      "Across one night in a coastal market, five strangers' stories quietly braid together.",
    tag: null,
    gradient: "linear-gradient(135deg,#9d174d,#6366f1)",
    status: "ready",
    manifestUrl: null,
  },
];
