import type { AudioTrack, ExtractTask, MediaInfo, Movie, SubtitleTrack, Tag } from "./types";
import { authHeader, getAdminToken, setAdminToken } from "./auth";
import {
  apiUrl,
  originUrl,
  beaconUrl,
  rewriteOriginUrl,
  hasBackendOverride,
  backendOverride,
  clearBackendOverride,
} from "./backend";

// Backend URLs are resolved at RUNTIME (see lib/backend.ts): a ?api= link or a
// stored value points the app at a Cloudflare-tunnel gateway, so the public
// viewer build on Render reaches a laptop-hosted backend without a rebuild.
// Local dev falls back to the per-service build defaults.
export {
  apiUrl,
  originUrl,
  beaconUrl,
  rewriteOriginUrl,
  hasBackendOverride,
  backendOverride,
  clearBackendOverride,
};

// Keep in sync with upload-api MAX_UPLOAD_SIZE_MB.
export const MAX_UPLOAD_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? 5000);

export type BeaconEvent = {
  event: "startup" | "rebuffer" | "bitrate_switch" | "error" | "heartbeat";
  timestamp: string;
  startup_ms?: number;
  rebuffer_ms?: number;
  current_bitrate_kbps?: number;
  error_type?: string;
};

/** Fire-and-forget QoE telemetry to the beacon-collector. */
export function sendBeacon(batch: {
  session_id: string;
  content_id?: string;
  player_version?: string;
  events: BeaconEvent[];
}): void {
  if (!batch.events.length) return;
  const body = JSON.stringify(batch);
  try {
    // sendBeacon survives page unload; fall back to fetch(keepalive).
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      navigator.sendBeacon(`${beaconUrl()}/api/v1/beacon/`, new Blob([body], { type: "application/json" }));
      return;
    }
  } catch {
    /* fall through */
  }
  void fetch(`${beaconUrl()}/api/v1/beacon/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {});
}

// ---- Live QoE stats (admin observability dashboard) ----

export type QoeStats = {
  window_seconds: number;
  generated_at: number;
  sessions: { total: number; active: number; rebuffer_free_pct: number };
  startup_ms: { count: number; p50: number; p95: number; avg: number };
  rebuffer: { events: number; sessions_affected: number; avg_ms: number; ratio: number };
  bitrate_kbps: { avg: number; p50: number };
  errors: { total: number; by_type: Record<string, number> };
  top_content: {
    content_id: string;
    sessions: number;
    startup_p95_ms: number;
    rebuffer_ratio: number;
  }[];
  recent_events: {
    ts: number;
    session_id: string;
    content_id: string | null;
    event: string;
    detail: string;
  }[];
};

/** Live rolling QoE aggregation from the beacon collector (admin dashboard). */
export async function fetchQoeStats(): Promise<QoeStats> {
  const res = await fetch(`${beaconUrl()}/api/v1/beacon/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error(`qoe stats failed: ${res.status}`);
  return (await res.json()) as QoeStats;
}

// ---- Backend wire shapes (snake_case) ----

type ApiMovie = {
  id: string;
  title: string;
  description?: string | null;
  genre: string;
  year: number;
  rating: string;
  duration?: string | null;
  tag?: string | null;
  manifest_url?: string | null;
  hdr_manifest_url?: string | null;
  dash_url?: string | null;
  storyboard_url?: string | null;
  thumbnail_url?: string | null;
  poster_url?: string | null;
  backdrop_url?: string | null;
  visibility?: "draft" | "published" | "unlisted" | null;
  status?: "processing" | "ready" | null;
  progress?: number | null;
  stage?: string | null;
  audio_tracks?: AudioTrack[];
  subtitle_tracks?: SubtitleTrack[];
  media_info?: MediaInfo | null;
  has_external_audio?: boolean | null;
  interp_requested?: boolean | null;
  interp_target_fps?: number | null;
  interp_status?: "queued" | "processing" | "done" | "skipped" | "failed" | null;
  interp_detail?: string | null;
  interp_manifest_url?: string | null;
  interp_fps?: number | null;
  interp_progress?: number | null;
  interp_stage?: string | null;
  interp_started_at?: number | null;
  extract_tasks?: ExtractTask[];
  created_at?: string;
};

export type UploadResponse = { job_id: string; status: string };
export type JobStatus = {
  job_id: string;
  status: "queued" | "processing" | "complete";
  stream_url: string | null;
  progress: number;
  stage: string | null;
};

export type MovieCreatePayload = {
  title: string;
  genre: string;
  year: number;
  rating: string;
  duration?: string;
  description?: string;
  tag?: string;
  manifest_url?: string;
  // I/O Framer (frame interpolation) — opt-in per upload.
  interp?: boolean;
  interp_target_fps?: number;
};

// I/O Framer feature flag + guardrails (public read).
export type InterpConfig = {
  enabled: boolean;
  default_target_fps: number;
  max_target_fps: number;
  max_height: number;
  max_source_fps: number;
  max_duration_seconds: number;
};

/** Read the interpolation feature flag + caps so the upload UI can show the
 *  toggle only when the server has it enabled. Best-effort (never throws in the
 *  caller path — treat a rejection as "disabled"). */
export async function getInterpConfig(): Promise<InterpConfig> {
  const res = await fetch(`${apiUrl()}/api/v1/interp/config`, { cache: "no-store" });
  if (!res.ok) throw new Error(`interp config failed: ${res.status}`);
  return (await res.json()) as InterpConfig;
}

// ---- Gradient synthesis (uploaded videos have no artwork) ----

const GRADIENTS = [
  "linear-gradient(135deg,#1e3a8a,#9333ea)",
  "linear-gradient(135deg,#be123c,#f59e0b)",
  "linear-gradient(135deg,#065f46,#22d3ee)",
  "linear-gradient(135deg,#7c2d12,#f43f5e)",
  "linear-gradient(135deg,#312e81,#06b6d4)",
  "linear-gradient(135deg,#4c1d95,#ec4899)",
  "linear-gradient(135deg,#0f766e,#84cc16)",
  "linear-gradient(135deg,#9d174d,#6366f1)",
];

export function gradientFor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) & 0xffffffff;
  }
  return GRADIENTS[Math.abs(hash) % GRADIENTS.length];
}

export function mapMovie(m: ApiMovie): Movie {
  return {
    id: m.id,
    title: m.title,
    genre: m.genre,
    year: m.year,
    rating: m.rating,
    duration: m.duration ?? "",
    description: m.description ?? "",
    tag: (m.tag as Tag) ?? null,
    gradient: gradientFor(m.id + m.title),
    status: m.status ?? "ready",
    // Playback + origin-served art are stored absolute against the transcode-time
    // origin (localhost:8080). rewriteOriginUrl() swaps the host for the runtime
    // gateway when a ?api= backend is set, and is a no-op locally / for external
    // (TMDB) art that isn't under /hls/.
    manifestUrl: rewriteOriginUrl(m.manifest_url ?? null),
    hdrManifestUrl: rewriteOriginUrl(m.hdr_manifest_url ?? null),
    dashUrl: rewriteOriginUrl(m.dash_url ?? null),
    // Effective poster shown on cards/hero: a custom upload wins over the
    // auto-extracted frame. posterUrl keeps the raw custom value for the admin.
    // Use `||` (not `??`) so a reset-to-auto empty string falls back correctly.
    thumbnailUrl: rewriteOriginUrl(m.poster_url || m.thumbnail_url || null),
    posterUrl: rewriteOriginUrl(m.poster_url || null),
    backdropUrl: rewriteOriginUrl(m.backdrop_url || m.poster_url || null),
    visibility: m.visibility ?? "published",
    progress: m.progress ?? 0,
    stage: m.stage ?? null,
    audioTracks: m.audio_tracks ?? [],
    subtitleTracks: (m.subtitle_tracks ?? []).map((t) => ({
      ...t,
      url: rewriteOriginUrl(t.url),
    })),
    mediaInfo: m.media_info ?? null,
    hasExternalAudio: m.has_external_audio ?? false,
    interpRequested: m.interp_requested ?? false,
    interpTargetFps: m.interp_target_fps ?? null,
    interpStatus: m.interp_status ?? null,
    interpDetail: m.interp_detail ?? null,
    storyboardUrl: rewriteOriginUrl(m.storyboard_url ?? null),
    interpManifestUrl: rewriteOriginUrl(m.interp_manifest_url ?? null),
    interpFps: m.interp_fps ?? null,
    interpProgress: m.interp_progress ?? null,
    interpStage: m.interp_stage ?? null,
    interpStartedAt: m.interp_started_at ?? null,
    extractTasks: m.extract_tasks ?? [],
  };
}

export async function getMovie(id: string): Promise<Movie | null> {
  const res = await fetch(`${apiUrl()}/api/v1/movies/${id}`, { cache: "no-store" });
  if (!res.ok) return null;
  return mapMovie((await res.json()) as ApiMovie);
}

// ---- API calls ----

export async function listMovies(): Promise<Movie[]> {
  const res = await fetch(`${apiUrl()}/api/v1/movies/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`listMovies failed: ${res.status}`);
  const data = (await res.json()) as { movies: ApiMovie[] };
  return data.movies.map(mapMovie);
}

export function uploadVideo(
  file: File,
  meta?: Partial<MovieCreatePayload>,
  onProgress?: (pct: number) => void,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (meta) {
    for (const [key, value] of Object.entries(meta)) {
      if (value !== undefined && value !== null && value !== "") {
        form.append(key, String(value));
      }
    }
  }
  // XHR (not fetch) so we get real upload-progress events.
  return new Promise<UploadResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${apiUrl()}/api/v1/upload`);
    const token = getAdminToken();
    if (token) xhr.setRequestHeader("Authorization", `Basic ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status === 401) {
        reject(new Error("Not authorized — log in as admin."));
      } else if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResponse);
        } catch {
          reject(new Error("Bad upload response"));
        }
      } else {
        reject(new Error(`upload failed: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload."));
    xhr.send(form);
  });
}

/** Verify admin credentials against upload-api and, on success, store them. */
export async function adminLogin(
  username: string,
  password: string,
): Promise<boolean> {
  const token = btoa(`${username}:${password}`);
  const res = await fetch(`${apiUrl()}/api/v1/admin/check`, {
    headers: { Authorization: `Basic ${token}` },
  });
  if (res.ok) {
    setAdminToken(username, password);
    return true;
  }
  return false;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${apiUrl()}/api/v1/jobs/${jobId}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`job status failed: ${res.status}`);
  return (await res.json()) as JobStatus;
}

/** Ask the worker to abort a still-processing transcode (admin only). */
export async function cancelJob(jobId: string): Promise<void> {
  const res = await fetch(`${apiUrl()}/api/v1/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: { ...authHeader() },
  });
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (res.status === 409) throw new Error("Job already finished — nothing to cancel.");
  if (res.status === 404) return; // already gone
  if (!res.ok) throw new Error(`cancel failed: ${res.status}`);
}

/** Delete an uploaded movie — catalog row + HLS segments + raw source (admin only). */
export async function deleteMovie(movieId: string): Promise<void> {
  const res = await fetch(`${apiUrl()}/api/v1/movies/${encodeURIComponent(movieId)}`, {
    method: "DELETE",
    headers: { ...authHeader() },
  });
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (res.status === 404) return; // already gone
  if (!res.ok && res.status !== 204) throw new Error(`delete failed: ${res.status}`);
}

export type MoviePatch = Partial<{
  title: string;
  description: string;
  genre: string;
  year: number;
  rating: string;
  tag: string;
  visibility: "draft" | "published" | "unlisted";
  // "" resets the poster to the auto-extracted frame; a URL pins a custom one.
  poster_url: string;
  backdrop_url: string;
}>;

/** Edit a title's metadata / visibility (admin). Returns the updated movie. */
export async function updateMovie(movieId: string, patch: MoviePatch): Promise<Movie> {
  const res = await fetch(`${apiUrl()}/api/v1/movies/${encodeURIComponent(movieId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(patch),
  });
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (!res.ok) throw new Error(`update failed: ${res.status}`);
  return mapMovie((await res.json()) as ApiMovie);
}

/** Upload custom poster (2:3) or backdrop (16:9) artwork for a title (admin). */
export async function uploadArtwork(
  movieId: string,
  file: File,
  kind: "poster" | "backdrop" = "poster",
): Promise<Movie> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(
    `${apiUrl()}/api/v1/movies/${encodeURIComponent(movieId)}/artwork?kind=${kind}`,
    { method: "POST", headers: { ...authHeader() }, body: form },
  );
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (!res.ok) throw new Error(`artwork upload failed: ${res.status}`);
  return mapMovie((await res.json()) as ApiMovie);
}

/** Attach an external audio track to a silent title, then re-transcode with it
    (admin). The clip re-segments with the new audio muxed in. */
export async function attachAudio(movieId: string, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(
    `${apiUrl()}/api/v1/movies/${encodeURIComponent(movieId)}/audio`,
    { method: "POST", headers: { ...authHeader() }, body: form },
  );
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (res.status === 409) throw new Error("Original source is gone — re-upload to add audio.");
  if (res.status === 400) throw new Error("Unsupported audio format (use mp3, m4a, aac, wav, ogg, opus or flac).");
  if (!res.ok && res.status !== 202) throw new Error(`attach audio failed: ${res.status}`);
}

/** Re-run the transcode from the original source (admin). */
export async function retranscodeMovie(movieId: string): Promise<void> {
  const res = await fetch(
    `${apiUrl()}/api/v1/movies/${encodeURIComponent(movieId)}/retranscode`,
    { method: "POST", headers: { ...authHeader() } },
  );
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (res.status === 409) throw new Error("Original source is gone — re-upload to re-transcode.");
  if (!res.ok && res.status !== 202) throw new Error(`re-transcode failed: ${res.status}`);
}

/** Add a NON-destructive smoothed (interpolated) rendition to a title via I/O
    Framer (admin). The original ladder is left intact; the worker publishes the
    smoothed one to {id}/interp/ and links it via interp_manifest_url, which the
    player exposes as a Smooth toggle. Skips + records a reason if the source is
    already high-fps / too tall / too long / HDR. */
export async function enhanceFps(movieId: string, targetFps: number): Promise<void> {
  const res = await fetch(
    `${apiUrl()}/api/v1/movies/${encodeURIComponent(movieId)}/interpolate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ target_fps: targetFps }),
    },
  );
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (res.status === 409) throw new Error("Source is gone, or interpolation is disabled on the server.");
  if (res.status === 400) throw new Error("Invalid target fps.");
  if (!res.ok && res.status !== 202) throw new Error(`add smooth failed: ${res.status}`);
}

/** Create a NEW interpolated (optionally downscaled) copy of a title — e.g. a 4K
    source smoothed into a 1080p·60fps copy. Leaves the original untouched (admin). */
export async function enhanceFpsCopy(
  movieId: string,
  targetFps: number,
  height?: number,
): Promise<void> {
  const res = await fetch(
    `${apiUrl()}/api/v1/movies/${encodeURIComponent(movieId)}/interpolate-copy`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ target_fps: targetFps, height: height ?? null }),
    },
  );
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (res.status === 409) throw new Error("Source is gone, or interpolation is disabled on the server.");
  if (res.status === 400) throw new Error("Invalid fps/height.");
  if (!res.ok && res.status !== 202) throw new Error(`create copy failed: ${res.status}`);
}

export async function createMovie(
  payload: MovieCreatePayload,
): Promise<Movie> {
  const res = await fetch(`${apiUrl()}/api/v1/movies/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(payload),
  });
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (!res.ok) throw new Error(`createMovie failed: ${res.status}`);
  return mapMovie((await res.json()) as ApiMovie);
}
