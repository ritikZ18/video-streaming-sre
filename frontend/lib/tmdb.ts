// TMDB catalog source — real posters + metadata for a rich browse experience.
// These titles are DISPLAY-ONLY (no playable HLS); only uploaded videos play.
// Requests go through the BACKEND proxy (upload-api /api/v1/tmdb/...), resolved
// at runtime so the static viewer reaches it through the tunnel gateway — the
// API key stays server-side. If TMDB isn't configured the proxy returns 503 and
// this module yields [] — the app falls back to the seed catalog + uploads.
import type { Genre, Movie } from "./types";
import { gradientFor, apiUrl } from "./api";

const img = (path: string | null | undefined, size: string): string | null =>
  path ? `https://image.tmdb.org/t/p/${size}${path}` : null;

// TMDB genre id → the app's five genre buckets (first match wins).
const GENRE_MAP: Record<number, Genre> = {
  28: "Action",
  12: "Action",
  10752: "Action",
  53: "Action",
  878: "Sci-Fi",
  14: "Sci-Fi",
  18: "Drama",
  10749: "Drama",
  36: "Drama",
  80: "Drama",
  35: "Comedy",
  16: "Comedy",
  99: "Documentary",
};

type TmdbMovie = {
  id: number;
  title: string;
  release_date?: string;
  vote_average?: number;
  overview?: string;
  poster_path?: string | null;
  backdrop_path?: string | null;
  genre_ids?: number[];
};

function toMovie(m: TmdbMovie): Movie | null {
  if (!m.poster_path) return null;
  const genre = (m.genre_ids ?? []).map((g) => GENRE_MAP[g]).find(Boolean) ?? "Drama";
  const year = m.release_date ? Number(m.release_date.slice(0, 4)) : 0;
  return {
    id: `tmdb-${m.id}`,
    title: m.title,
    genre,
    year: year || 0,
    rating: m.vote_average ? `${m.vote_average.toFixed(1)} ★` : "NR",
    duration: "",
    description: m.overview ?? "",
    tag: null,
    gradient: gradientFor(`tmdb-${m.id}`),
    status: "ready",
    manifestUrl: null, // not playable — catalog only
    thumbnailUrl: img(m.poster_path, "w342"),
    backdropUrl: img(m.backdrop_path, "w1280"),
    displayOnly: true,
  };
}

async function fetchPage(p: number): Promise<TmdbMovie[]> {
  try {
    const res = await fetch(`${apiUrl()}/api/v1/tmdb/movie/popular?page=${p}`, {
      cache: "force-cache",
    });
    if (!res.ok) return [];
    const data = (await res.json()) as { results?: TmdbMovie[] };
    return data.results ?? [];
  } catch {
    return [];
  }
}

/** Fetch ~`target` popular movies (20/page) via the proxy, mapped + deduped. */
export async function fetchTmdbCatalog(target = 500): Promise<Movie[]> {
  const pages = Math.min(25, Math.max(1, Math.ceil(target / 20)));
  const batches = await Promise.all(
    Array.from({ length: pages }, (_, i) => fetchPage(i + 1)),
  );
  const seen = new Set<string>();
  const out: Movie[] = [];
  for (const arr of batches) {
    for (const m of arr) {
      const mv = toMovie(m);
      if (mv && !seen.has(mv.id)) {
        seen.add(mv.id);
        out.push(mv);
      }
    }
  }
  return out;
}
