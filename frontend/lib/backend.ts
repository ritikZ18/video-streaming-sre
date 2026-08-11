// Runtime resolution of the backend base URL (a Cloudflare-tunnel gateway), so
// the public viewer UI on Render can point at a laptop-hosted backend whose
// hostname changes every restart — WITHOUT a rebuild. Resolution order:
//   1. ?api=<url> in the address bar   (stored, then stripped from the URL)
//   2. a value a previous visit stored  (localStorage)
//   3. the build-time NEXT_PUBLIC_* default  (local dev / same-host deploy)
//
// A single gateway multiplexes upload-api, beacon-collector and the origin by
// path, so ONE base covers all three; local dev keeps three separate ports.

// Build-time flag for the public "viewer" deployment (Render sets it to "1"):
// hides admin/ops surfaces so the shipped UI is browse + play only. Off locally,
// so the full admin studio still works.
export const VIEWER_ONLY = process.env.NEXT_PUBLIC_VIEWER_ONLY === "1";

const STORAGE_KEY = "streamsre.backendBase";

// The value can arrive from a query param, which is attacker-controlled if
// someone is handed a crafted link. Only http(s) may ever be stored or fetched —
// `javascript:` must never reach storage, let alone become a fetch target.
function isValidHttpUrl(candidate: string): boolean {
  try {
    const u = new URL(candidate.trim());
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function normalize(u: string): string {
  return u.trim().replace(/\/+$/, "");
}

/** The runtime backend base (gateway) if one was provided, else null (→ use the
 *  build-time per-service defaults for local dev). Adopts ?api= on first sight. */
export function backendBase(): string | null {
  if (typeof window === "undefined") return null; // SSR → build defaults
  try {
    const fromQuery = new URLSearchParams(window.location.search).get("api");
    if (fromQuery && isValidHttpUrl(fromQuery)) {
      const value = normalize(fromQuery);
      window.localStorage.setItem(STORAGE_KEY, value);
      // Strip ?api= from the address bar once stored: otherwise the tunnel
      // address rides along in every share and lingers in history after it dies.
      const clean = new URL(window.location.href);
      clean.searchParams.delete("api");
      window.history.replaceState({}, "", clean.toString());
      return value;
    }
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && isValidHttpUrl(stored)) return normalize(stored);
  } catch {
    /* localStorage/history can throw in locked-down browsers — fall through */
  }
  return null;
}

function buildDefault(envUrl: string | undefined, fallback: string): string {
  return envUrl && envUrl.length ? normalize(envUrl) : fallback;
}

export function apiUrl(): string {
  return backendBase() ?? buildDefault(process.env.NEXT_PUBLIC_API_URL, "http://localhost:8000");
}
export function originUrl(): string {
  return backendBase() ?? buildDefault(process.env.NEXT_PUBLIC_ORIGIN_URL, "http://localhost:8080");
}
export function beaconUrl(): string {
  return backendBase() ?? buildDefault(process.env.NEXT_PUBLIC_BEACON_URL, "http://localhost:8001");
}

/** Playback assets are stored absolute against the transcode-time origin
 *  (e.g. http://localhost:8080/hls/<id>/master.m3u8). When a runtime backend
 *  base is set, swap the host so the media loads through the tunnel gateway.
 *  Only /hls/ paths are origin-served; external art (e.g. TMDB) is left as-is. */
export function rewriteOriginUrl<T extends string | null | undefined>(url: T): T {
  const base = backendBase();
  if (!url || !base) return url;
  try {
    const u = new URL(url, base);
    if (u.pathname.startsWith("/hls/")) {
      return (normalize(base) + u.pathname + u.search) as T;
    }
  } catch {
    /* not a parseable URL — leave it */
  }
  return url;
}

/** True once the viewer has adopted a runtime backend (via ?api=). */
export function hasBackendOverride(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return !!window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return false;
  }
}

/** The currently stored backend base, if any (for a "connected to …" hint). */
export function backendOverride(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Forget the stored backend so a device that cached a dead tunnel can recover. */
export function clearBackendOverride(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
