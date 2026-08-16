// Live-streaming API client. Public reads (list/get) are sanitized; admin calls
// (create/start/stop/delete/full-list) send the stored admin Basic credentials.
import { apiUrl, rewriteOriginUrl } from "./backend";
import { authHeader } from "./auth";
import type { LiveEvent, LiveState } from "./types";

// ---- wire shapes (snake_case) ----
type ApiLiveEvent = {
  id: string;
  title: string;
  description?: string | null;
  source_type: "ingest" | "playout";
  state: LiveState;
  audio_only?: boolean | null;
  manifest_url?: string | null;
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  started_at?: string | null;
  poster_url?: string | null;
  backdrop_url?: string | null;
};

// The admin projection additionally carries the secret publish key + push URL.
type ApiLiveEventAdmin = ApiLiveEvent & {
  created_at?: string;
  stream_key?: string | null;
  ingest_url?: string | null;
  ingest_protocol?: "rtmp" | "srt" | "whip";
  playout_source_movie_id?: string | null;
  loop?: boolean | null;
  max_height?: number | null;
  ended_at?: string | null;
  error_detail?: string | null;
};

export type LiveEventAdmin = LiveEvent & {
  createdAt?: string | null;
  streamKey?: string | null;
  ingestUrl?: string | null;
  ingestProtocol?: "rtmp" | "srt" | "whip";
  playoutSourceMovieId?: string | null;
  loop?: boolean;
  maxHeight?: number | null;
  endedAt?: string | null;
  errorDetail?: string | null;
};

export type CreateLiveEventPayload = {
  title: string;
  description?: string;
  source_type: "ingest" | "playout";
  audio_only?: boolean;
  max_height?: number;
  playout_source_movie_id?: string;
  loop?: boolean;
  ingest_protocol?: "rtmp" | "srt" | "whip";
  /** ISO timestamp; when set the channel is created "scheduled" and the backend
   *  scheduler auto-starts it at this time. */
  scheduled_start?: string;
  scheduled_end?: string;
  /** Keep the stream as a replay VOD when it ends (no re-encode — the live
   *  segments are already an ABR ladder). */
  record_to_vod?: boolean;
};

function mapLive(e: ApiLiveEvent): LiveEvent {
  return {
    id: e.id,
    title: e.title,
    description: e.description ?? null,
    sourceType: e.source_type,
    state: e.state,
    audioOnly: Boolean(e.audio_only),
    manifestUrl: rewriteOriginUrl(e.manifest_url ?? null),
    scheduledStart: e.scheduled_start ?? null,
    scheduledEnd: e.scheduled_end ?? null,
    startedAt: e.started_at ?? null,
    posterUrl: rewriteOriginUrl(e.poster_url ?? null),
    backdropUrl: rewriteOriginUrl(e.backdrop_url ?? null),
  };
}

function mapLiveAdmin(e: ApiLiveEventAdmin): LiveEventAdmin {
  return {
    ...mapLive(e),
    createdAt: e.created_at ?? null,
    streamKey: e.stream_key ?? null,
    ingestUrl: e.ingest_url ?? null,
    ingestProtocol: e.ingest_protocol,
    playoutSourceMovieId: e.playout_source_movie_id ?? null,
    loop: Boolean(e.loop),
    maxHeight: e.max_height ?? null,
    endedAt: e.ended_at ?? null,
    errorDetail: e.error_detail ?? null,
  };
}

// ---- public reads ----
export async function listLiveEvents(): Promise<LiveEvent[]> {
  const res = await fetch(`${apiUrl()}/api/v1/live/events`, { cache: "no-store" });
  if (!res.ok) throw new Error(`listLiveEvents failed: ${res.status}`);
  const data = (await res.json()) as { events: ApiLiveEvent[] };
  return (data.events ?? []).map(mapLive);
}

export async function getLiveEvent(id: string): Promise<LiveEvent | null> {
  const res = await fetch(`${apiUrl()}/api/v1/live/events/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return mapLive((await res.json()) as ApiLiveEvent);
}

// ---- admin ----
export async function adminListLiveEvents(): Promise<LiveEventAdmin[]> {
  const res = await fetch(`${apiUrl()}/api/v1/live/admin/events`, {
    cache: "no-store",
    headers: { ...authHeader() },
  });
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (!res.ok) throw new Error(`admin live list failed: ${res.status}`);
  const data = (await res.json()) as { events: ApiLiveEventAdmin[] };
  return (data.events ?? []).map(mapLiveAdmin);
}

export async function createLiveEvent(
  payload: CreateLiveEventPayload,
): Promise<LiveEventAdmin> {
  const res = await fetch(`${apiUrl()}/api/v1/live/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(payload),
  });
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (res.status === 400) throw new Error((await safeDetail(res)) || "Invalid live event.");
  if (!res.ok && res.status !== 201) throw new Error(`create live failed: ${res.status}`);
  return mapLiveAdmin((await res.json()) as ApiLiveEventAdmin);
}

export async function startLiveEvent(id: string): Promise<LiveEventAdmin> {
  return actOnEvent(id, "start");
}

export async function stopLiveEvent(id: string): Promise<LiveEventAdmin> {
  return actOnEvent(id, "stop");
}

async function actOnEvent(id: string, action: "start" | "stop"): Promise<LiveEventAdmin> {
  const res = await fetch(
    `${apiUrl()}/api/v1/live/events/${encodeURIComponent(id)}/${action}`,
    { method: "POST", headers: { ...authHeader() } },
  );
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (res.status === 409) throw new Error((await safeDetail(res)) || "Channel not ready.");
  if (!res.ok) throw new Error(`${action} live failed: ${res.status}`);
  return mapLiveAdmin((await res.json()) as ApiLiveEventAdmin);
}

export async function deleteLiveEvent(id: string): Promise<void> {
  const res = await fetch(`${apiUrl()}/api/v1/live/events/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: { ...authHeader() },
  });
  if (res.status === 401) throw new Error("Not authorized — log in as admin.");
  if (res.status === 404) return;
  if (!res.ok && res.status !== 204) throw new Error(`delete live failed: ${res.status}`);
}

async function safeDetail(res: Response): Promise<string | null> {
  try {
    const body = (await res.json()) as { detail?: string };
    return body.detail ?? null;
  } catch {
    return null;
  }
}
