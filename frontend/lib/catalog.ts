import type { Movie } from "./types";

/** Normalize a title for dedup: lowercase, collapse whitespace, strip trailing junk. */
export function titleKey(title: string): string {
  return title
    .trim()
    .toLowerCase()
    .replace(/\.[a-z0-9]{2,4}$/i, "") // stray extension
    .replace(/\s+/g, " ");
}

/**
 * Collapse duplicate titles, keeping the FIRST occurrence. Callers put playable
 * uploads before TMDB entries, and newest-first within uploads, so the kept copy
 * is the best one. Fixes the same video appearing under multiple genre rows.
 */
export function dedupeByTitle(movies: Movie[]): Movie[] {
  const seen = new Set<string>();
  const out: Movie[] = [];
  for (const m of movies) {
    const key = titleKey(m.title);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(m);
  }
  return out;
}

/** Set of normalized titles already in the catalog (to reject duplicate uploads). */
export function titleSet(movies: Movie[]): Set<string> {
  return new Set(movies.map((m) => titleKey(m.title)));
}
