import type { Movie, Tag } from "./types";
import { authHeader, getAdminToken, setAdminToken } from "./auth";

// The browser talks to the host-exposed ports. Override at build time with
// NEXT_PUBLIC_API_URL / NEXT_PUBLIC_ORIGIN_URL if you remap them.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const ORIGIN_URL =
  process.env.NEXT_PUBLIC_ORIGIN_URL ?? "http://localhost:8080";

// Keep in sync with upload-api MAX_UPLOAD_SIZE_MB.
export const MAX_UPLOAD_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? 5000);

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
  dash_url?: string | null;
  thumbnail_url?: string | null;
  status?: "processing" | "ready" | null;
  progress?: number | null;
  created_at?: string;
};

export type UploadResponse = { job_id: string; status: string };
export type JobStatus = {
  job_id: string;
  status: "queued" | "processing" | "complete";
  stream_url: string | null;
  progress: number;
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
};

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
    manifestUrl: m.manifest_url ?? null,
    dashUrl: m.dash_url ?? null,
    thumbnailUrl: m.thumbnail_url ?? null,
    progress: m.progress ?? 0,
  };
}

// ---- API calls ----

export async function listMovies(): Promise<Movie[]> {
  const res = await fetch(`${API_URL}/api/v1/movies/`, { cache: "no-store" });
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
    xhr.open("POST", `${API_URL}/api/v1/upload`);
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
  const res = await fetch(`${API_URL}/api/v1/admin/check`, {
    headers: { Authorization: `Basic ${token}` },
  });
  if (res.ok) {
    setAdminToken(username, password);
    return true;
  }
  return false;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_URL}/api/v1/jobs/${jobId}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`job status failed: ${res.status}`);
  return (await res.json()) as JobStatus;
}

export async function createMovie(
  payload: MovieCreatePayload,
): Promise<Movie> {
  const res = await fetch(`${API_URL}/api/v1/movies/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(payload),
  });
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (!res.ok) throw new Error(`createMovie failed: ${res.status}`);
  return mapMovie((await res.json()) as ApiMovie);
}
